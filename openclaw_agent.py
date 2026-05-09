"""
openclaw_agent.py — Integrasi OpenClaw untuk Nexus DualBrain AI
================================================================
OpenClaw adalah AI agent gateway open-source yang menghubungkan
Telegram (dan platform chat lain) ke LLM (Gemini, Claude, dll).

Dalam Nexus DualBrain:
  - OpenClaw menggantikan TelegramAgent biasa dengan interface yang lebih kaya
  - User bisa kirim perintah via Telegram → OpenClaw memprosesnya
  - OpenClaw mengelola routing LLM dan konteks percakapan

Cara penggunaan:
  1. Install: pip install openclaw-sdk
  2. Set OPENCLAW_API_KEY dan OPENCLAW_GATEWAY_URL di .env
  3. OpenClawAgent akan otomatis aktif jika key tersedia
  4. Jika tidak ada key, fallback ke TelegramAgent biasa

Referensi: https://docs.openclaw.ai
"""

import os
import logging
import json
import time
import threading
import requests
from typing import Optional, Callable

logger = logging.getLogger(__name__)


# ─── Perintah yang diterima via OpenClaw/Telegram ───
COMMANDS = {
    "/status":   "Tampilkan status agent dan ringkasan finansial",
    "/pause":    "Pause agent sementara (tidak cari job baru)",
    "/resume":   "Lanjutkan agent setelah pause",
    "/jobs":     "Tampilkan job yang sedang dikerjakan",
    "/earnings": "Tampilkan ringkasan pendapatan",
    "/help":     "Tampilkan daftar perintah",
}


class OpenClawAgent:
    """
    Agent OpenClaw terintegrasi untuk Nexus DualBrain.
    Menangani komunikasi dua-arah antara user (Telegram) dan workflow agent.
    """

    def __init__(self, gemini_client=None):
        self.api_key = os.environ.get("OPENCLAW_API_KEY", "")
        self.gateway_url = os.environ.get("OPENCLAW_GATEWAY_URL", "https://api.getopenclaw.ai")
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.llm = gemini_client

        self._paused = False
        self._lock = threading.Lock()
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_update_id = 0

        # Deteksi mode: OpenClaw SDK atau fallback Telegram biasa
        self.use_openclaw = bool(self.api_key)
        if self.use_openclaw:
            logger.info("[OpenClaw] Mode aktif: OpenClaw Gateway (full features)")
        else:
            logger.info("[OpenClaw] Mode fallback: Telegram direct (OPENCLAW_API_KEY tidak di-set)")

    # ─────────────────────────────────────────────
    # SEND: Kirim pesan ke user
    # ─────────────────────────────────────────────

    def send_message(self, text: str, markdown: bool = False) -> bool:
        """Kirim pesan notifikasi ke user via OpenClaw atau Telegram langsung."""
        if not text:
            return False

        if self.use_openclaw:
            return self._send_via_openclaw(text)
        else:
            return self._send_via_telegram(text, markdown)

    def send_document(self, file_path: str, caption: str = "") -> bool:
        """Kirim file hasil kerja ke user."""
        if self.use_openclaw:
            # OpenClaw: upload file ke gateway lalu forward ke Telegram
            return self._send_file_via_openclaw(file_path, caption)
        else:
            return self._send_file_via_telegram(file_path, caption)

    def _send_via_openclaw(self, text: str) -> bool:
        """Kirim pesan melalui OpenClaw Gateway API."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "message": text,
                "channel": "telegram",
                "chat_id": self.chat_id
            }
            resp = requests.post(
                f"{self.gateway_url}/v1/send",
                headers=headers,
                json=payload,
                timeout=15
            )
            if resp.status_code == 200:
                return True
            # Fallback ke telegram langsung jika OpenClaw gagal
            logger.warning(f"[OpenClaw] Gateway error {resp.status_code}. Fallback ke Telegram.")
            return self._send_via_telegram(text)
        except Exception as e:
            logger.error(f"[OpenClaw] Send gagal: {e}. Fallback ke Telegram.")
            return self._send_via_telegram(text)

    def _send_via_telegram(self, text: str, markdown: bool = False) -> bool:
        """Kirim pesan langsung via Telegram Bot API."""
        if not self.telegram_token or not self.chat_id:
            logger.warning("[OpenClaw] Tidak ada Telegram token/chat_id. Pesan tidak terkirim.")
            return False
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text[:4096],  # Telegram max 4096 chars
            }
            if markdown:
                payload["parse_mode"] = "Markdown"
            resp = requests.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json=payload,
                timeout=15
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"[Telegram] Send gagal: {e}")
            return False

    def _send_file_via_openclaw(self, file_path: str, caption: str) -> bool:
        """Upload file melalui OpenClaw gateway."""
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{self.gateway_url}/v1/send_file",
                    headers=headers,
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"file": f},
                    timeout=30
                )
            if resp.status_code == 200:
                return True
            return self._send_file_via_telegram(file_path, caption)
        except Exception as e:
            logger.error(f"[OpenClaw] File send gagal: {e}")
            return self._send_file_via_telegram(file_path, caption)

    def _send_file_via_telegram(self, file_path: str, caption: str) -> bool:
        """Kirim file langsung via Telegram Bot API."""
        if not self.telegram_token or not self.chat_id:
            return False
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendDocument",
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"document": f},
                    timeout=30
                )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"[Telegram] File send gagal: {e}")
            return False

    # ─────────────────────────────────────────────
    # RECEIVE: Polling perintah dari user
    # ─────────────────────────────────────────────

    def start_command_listener(self, status_callback: Callable = None, finance_callback: Callable = None):
        """
        Mulai background thread untuk polling perintah dari user via Telegram.
        status_callback: fungsi yang mengembalikan dict status agent
        finance_callback: fungsi yang mengembalikan dict summary keuangan
        """
        self._running = True
        self._status_cb = status_callback
        self._finance_cb = finance_callback
        self._poll_thread = threading.Thread(
            target=self._polling_loop,
            name="OpenClawPoll",
            daemon=True
        )
        self._poll_thread.start()
        logger.info("[OpenClaw] Command listener aktif.")

    def stop_command_listener(self):
        """Hentikan polling thread."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        logger.info("[OpenClaw] Command listener dihentikan.")

    def _polling_loop(self):
        """Loop polling update dari Telegram setiap 5 detik."""
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
            except Exception as e:
                logger.error(f"[OpenClaw] Polling error: {e}")
            time.sleep(5)

    def _get_updates(self) -> list:
        """Ambil update baru dari Telegram Bot API."""
        if not self.telegram_token:
            return []
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{self.telegram_token}/getUpdates",
                params={"offset": self._last_update_id + 1, "timeout": 5},
                timeout=10
            )
            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                if updates:
                    self._last_update_id = updates[-1]["update_id"]
                return updates
        except Exception as e:
            logger.debug(f"[OpenClaw] getUpdates error: {e}")
        return []

    def _handle_update(self, update: dict):
        """Proses perintah dari user."""
        message = update.get("message", {})
        text = message.get("text", "").strip()
        if not text:
            return

        logger.info(f"[OpenClaw] Perintah diterima: {text}")

        cmd = text.split()[0].lower()

        if cmd == "/status":
            self._handle_status()
        elif cmd == "/pause":
            with self._lock:
                self._paused = True
            self.send_message("⏸️ Agent dijeda. Kirim /resume untuk melanjutkan.")
        elif cmd == "/resume":
            with self._lock:
                self._paused = False
            self.send_message("▶️ Agent dilanjutkan.")
        elif cmd == "/jobs":
            self.send_message("📋 Fitur log job aktif akan ditambahkan di update berikutnya.")
        elif cmd == "/earnings":
            self._handle_earnings()
        elif cmd == "/help":
            help_text = "🦞 *Nexus DualBrain AI — Perintah Tersedia:*\n\n"
            help_text += "\n".join([f"`{cmd}` — {desc}" for cmd, desc in COMMANDS.items()])
            self.send_message(help_text, markdown=True)
        else:
            # Kirim ke LLM untuk respons bebas (conversational mode)
            if self.llm:
                response = self.llm.generate_content(
                    f"Kamu adalah asisten AI freelance bernama Nexus. "
                    f"Jawab pertanyaan user ini dengan singkat dan informatif:\n{text}",
                    use_codegen_model=False
                )
                if response:
                    self.send_message(f"🤖 {response[:1000]}")

    def _handle_status(self):
        """Kirim status agent ke user."""
        if self._status_cb:
            try:
                status = self._status_cb()
                paused_str = "⏸️ DIJEDA" if self._paused else "▶️ AKTIF"
                msg = (
                    f"📊 *Status Nexus DualBrain AI*\n\n"
                    f"Mode: {paused_str}\n"
                    f"Step saat ini: {status.get('current_step', 'N/A')}\n"
                    f"Task ID: {status.get('task_id', 'N/A')[:8]}...\n"
                    f"Uptime: {status.get('uptime', 'N/A')}"
                )
                self.send_message(msg, markdown=True)
            except Exception as e:
                self.send_message(f"❌ Gagal ambil status: {e}")
        else:
            paused = "DIJEDA" if self._paused else "AKTIF"
            self.send_message(f"Status: {paused}")

    def _handle_earnings(self):
        """Kirim ringkasan keuangan ke user."""
        if self._finance_cb:
            try:
                summary = self._finance_cb()
                msg = (
                    f"💰 *Ringkasan Keuangan*\n\n"
                    f"Job selesai: {summary.get('completed_jobs', 0)}\n"
                    f"Total pendapatan: ${summary.get('total_revenue', 0):.2f}\n"
                    f"Job dipropose: {summary.get('total_proposals', 0)}"
                )
                self.send_message(msg, markdown=True)
            except Exception as e:
                self.send_message(f"❌ Gagal ambil data keuangan: {e}")

    # ─────────────────────────────────────────────
    # CONTROL: State check
    # ─────────────────────────────────────────────

    @property
    def is_paused(self) -> bool:
        """Cek apakah agent sedang dijeda oleh user."""
        with self._lock:
            return self._paused
