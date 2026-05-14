"""
hermes_agent.py — Integrasi Hermes Agent untuk Nexus DualBrain AI
================================================================
Hermes Agent (by NousResearch) adalah framework AI agent otonom
open-source dengan fitur self-improving learning loop, persistent
memory, dan multi-platform gateway (Telegram, Discord, Slack).

Dalam Nexus DualBrain:
  - Hermes Agent menggantikan TelegramAgent biasa dengan interface yang lebih kaya
  - User bisa kirim perintah via Telegram → Hermes Agent memprosesnya
  - Hermes Agent mengelola routing LLM dan konteks percakapan
  - Hermes Agent membangun skill library secara otomatis dari task yang berhasil

Cara penggunaan:
  1. Install: pip install git+https://github.com/NousResearch/hermes-agent.git
  2. Set HERMES_API_KEY dan HERMES_GATEWAY_URL di .env
  3. HermesAgent akan otomatis aktif jika key tersedia
  4. Jika tidak ada key, fallback ke TelegramAgent biasa

Referensi: https://github.com/NousResearch/hermes-agent
"""

import os
import logging
import json
import time
import threading
import requests
from typing import Optional, Callable

logger = logging.getLogger(__name__)


# ─── Perintah yang diterima via Hermes Agent/Telegram ───
COMMANDS = {
    "/status":   "Tampilkan status agent, uptime, dan cycle count",
    "/pause":    "Pause agent sementara (tidak cari job baru)",
    "/resume":   "Lanjutkan agent setelah pause",
    "/jobs":     "Tampilkan job aktif di queue",
    "/earnings": "Tampilkan ringkasan pendapatan total",
    "/income":   "Pendapatan hari ini + 7 hari terakhir",
    "/apply":    "Trigger pencarian job sekarang (bypass jadwal)",
    "/think":    "Trigger self-reflection AGI sekarang",
    "/skills":   "Tampilkan statistik skill library",
    "/test":     "Test koneksi Telegram (ping)",
    "/help":     "Tampilkan daftar perintah ini",
}


class HermesAgent:
    """
    Hermes Agent terintegrasi untuk Nexus DualBrain.
    Menangani komunikasi dua-arah antara user (Telegram) dan workflow agent.
    Memanfaatkan self-improving learning loop dari Hermes Agent framework.
    """

    def __init__(self, gemini_client=None):
        self.api_key = os.environ.get("HERMES_API_KEY", "")
        self.gateway_url = os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:18789")
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.llm = gemini_client

        self._paused = False
        self._lock = threading.Lock()
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_update_id = 0

        # Deteksi mode: Hermes Gateway atau fallback Telegram biasa
        self.use_hermes = bool(self.api_key)
        if self.use_hermes:
            logger.info("[Hermes] Mode aktif: Hermes Agent Gateway (full features)")
        else:
            logger.info("[Hermes] Mode fallback: Telegram direct (HERMES_API_KEY tidak di-set)")

        # Persistent memory for Telegram conversation
        self.memory_file = os.path.join(os.path.dirname(__file__), "output", "hermes_chat_history.json")
        self.chat_history = self._load_memory()

    def _load_memory(self) -> list:
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"[Hermes] Gagal memuat memori percakapan: {e}")
        return []

    def _save_memory(self):
        try:
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            # Keep only last 20 messages to prevent token bloat
            if len(self.chat_history) > 20:
                self.chat_history = self.chat_history[-20:]
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.chat_history, f, indent=4)
        except Exception as e:
            logger.error(f"[Hermes] Gagal menyimpan memori percakapan: {e}")

    # ─────────────────────────────────────────────
    # SEND: Kirim pesan ke user
    # ─────────────────────────────────────────────

    def send_message(self, text: str, markdown: bool = False) -> bool:
        """Kirim pesan notifikasi ke user via Hermes Agent atau Telegram langsung."""
        if not text:
            return False

        if self.use_hermes:
            return self._send_via_hermes(text)
        else:
            return self._send_via_telegram(text, markdown)

    def send_document(self, file_path: str, caption: str = "") -> bool:
        """Kirim file hasil kerja ke user."""
        if self.use_hermes:
            # Hermes Agent: upload file ke gateway lalu forward ke Telegram
            return self._send_file_via_hermes(file_path, caption)
        else:
            return self._send_file_via_telegram(file_path, caption)

    def _send_via_hermes(self, text: str) -> bool:
        """Kirim pesan melalui Hermes Agent Gateway API."""
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
            # Fallback ke telegram langsung jika Hermes Gateway gagal
            logger.warning(f"[Hermes] Gateway error {resp.status_code}. Fallback ke Telegram.")
            return self._send_via_telegram(text)
        except Exception as e:
            logger.error(f"[Hermes] Send gagal: {e}. Fallback ke Telegram.")
            return self._send_via_telegram(text)

    def _send_via_telegram(self, text: str, markdown: bool = False) -> bool:
        """Kirim pesan langsung via Telegram Bot API, dengan retry 3x."""
        if not self.telegram_token or not self.chat_id:
            logger.warning("[Hermes] TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID tidak di-set di .env!")
            return False
        payload = {
            "chat_id": self.chat_id,
            "text": text[:4096],
        }
        if markdown:
            payload["parse_mode"] = "MarkdownV2" if False else "Markdown"
        for attempt in range(1, 4):  # retry 3x
            try:
                resp = requests.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    json=payload,
                    timeout=15
                )
                if resp.status_code == 200:
                    return True
                # Jika parse error, coba kirim tanpa markdown
                err = resp.json().get("description", "")
                logger.warning("[Telegram] Attempt %d gagal: %s %s", attempt, resp.status_code, err)
                if "parse" in err.lower() and markdown:
                    logger.info("[Telegram] Retry tanpa Markdown formatting.")
                    payload.pop("parse_mode", None)
                    markdown = False
            except requests.exceptions.ConnectionError:
                logger.error("[Telegram] Tidak bisa connect ke api.telegram.org. Cek koneksi internet WSL.")
                return False
            except Exception as e:
                logger.error("[Telegram] Attempt %d error: %s", attempt, e)
            time.sleep(2)
        return False

    def _send_file_via_hermes(self, file_path: str, caption: str) -> bool:
        """Upload file melalui Hermes Agent gateway."""
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
            logger.error(f"[Hermes] File send gagal: {e}")
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
            name="HermesPoll",
            daemon=True
        )
        self._poll_thread.start()
        logger.info("[Hermes] Command listener aktif.")

    def stop_command_listener(self):
        """Hentikan polling thread."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        logger.info("[Hermes] Command listener dihentikan.")

    def _polling_loop(self):
        """Loop polling update dari Telegram setiap 5 detik."""
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
            except Exception as e:
                logger.error(f"[Hermes] Polling error: {e}")
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
            logger.debug(f"[Hermes] getUpdates error: {e}")
        return []

    def _handle_update(self, update: dict):
        """Proses perintah dari user."""
        message = update.get("message", {})
        text = message.get("text", "").strip()
        if not text:
            return

        logger.info(f"[Hermes] Perintah diterima: {text}")

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
            self._handle_jobs()
        elif cmd == "/earnings":
            self._handle_earnings()
        elif cmd == "/income":
            self._handle_income()
        elif cmd == "/apply":
            self._handle_apply()
        elif cmd == "/think":
            self._handle_think()
        elif cmd == "/skills":
            self._handle_skills()
        elif cmd == "/test":
            self._handle_test()
        elif cmd == "/help":
            help_text = "🧠 *Nexus DualBrain AI — Perintah:*\n\n"
            help_text += "\n".join([f"`{c}` — {d}" for c, d in COMMANDS.items()])
            self.send_message(help_text, markdown=True)
        else:
            # Kirim ke LLM untuk respons bebas (conversational mode)
            if self.llm:
                # Tambahkan ke memori
                self.chat_history.append({"role": "user", "content": text})
                
                # Buat konteks percakapan
                history_text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in self.chat_history])
                
                prompt = (
                    f"Kamu adalah asisten AI freelance bernama Nexus.\n"
                    f"Berikut adalah riwayat percakapan kita:\n{history_text}\n\n"
                    f"Berdasarkan konteks di atas, jawab pertanyaan user terbaru dengan singkat dan informatif (max 200 kata)."
                )
                
                response = self.llm.generate_content(
                    prompt,
                    use_codegen_model=False
                )
                if response:
                    self.chat_history.append({"role": "nexus", "content": response})
                    self._save_memory()
                    self.send_message(f"🤖 {response[:1000]}")
            else:
                self.send_message("Perintah tidak dikenal. Ketik /help untuk daftar perintah.")

    def _handle_status(self):
        """Kirim status agent ke user."""
        if self._status_cb:
            try:
                status = self._status_cb()
                paused_str = "⏸️ DIJEDA" if self._paused else "▶️ AKTIF"
                msg = (
                    f"📊 *Status Nexus DualBrain AI (Hermes)*\n\n"
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
                    f"Pending: ${summary.get('pending_revenue', 0):.2f}\n"
                    f"Proposal terkirim: {summary.get('total_proposals', 0)}"
                )
                self.send_message(msg, markdown=True)
            except Exception as e:
                self.send_message(f"❌ Gagal ambil data keuangan: {e}")
        else:
            self.send_message("❌ Financial tracker tidak terhubung.")

    def _handle_income(self):
        """Pendapatan hari ini dan 7 hari terakhir."""
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(__file__), "output", "financial.db")
            if not os.path.exists(db_path):
                self.send_message("📊 Belum ada data pendapatan (database kosong).")
                return
            with sqlite3.connect(db_path) as conn:
                today = conn.execute(
                    "SELECT SUM(revenue) FROM earnings WHERE date(created_at) = date('now')"
                ).fetchone()[0] or 0
                week = conn.execute(
                    "SELECT SUM(revenue) FROM earnings WHERE created_at >= datetime('now','-7 days')"
                ).fetchone()[0] or 0
                count_week = conn.execute(
                    "SELECT COUNT(*) FROM earnings WHERE created_at >= datetime('now','-7 days')"
                ).fetchone()[0] or 0
            self.send_message(
                f"📊 *Income Report*\n\n"
                f"Hari ini: ${today:.2f}\n"
                f"7 hari terakhir: ${week:.2f}\n"
                f"Job selesai 7 hari: {count_week}",
                markdown=True
            )
        except Exception as e:
            self.send_message(f"❌ Gagal ambil data income: {e}")

    def _handle_jobs(self):
        """Tampilkan job aktif dari job_queue.json."""
        try:
            import json
            queue_path = os.path.join(os.path.dirname(__file__), "output", "job_queue.json")
            if not os.path.exists(queue_path):
                self.send_message("📋 Job queue kosong.")
                return
            with open(queue_path) as f:
                jobs = json.load(f)
            active = [j for j in jobs if j.get("status") not in ["DELIVERED", "PAID", "CANCELLED"]]
            if not active:
                self.send_message("📋 Tidak ada job aktif saat ini.")
                return
            lines = ["📋 *Job Aktif:*\n"]
            for j in active[:5]:
                lines.append(
                    f"• [{j.get('status','?')}] {j.get('title','?')[:40]}\n"
                    f"  Platform: {j.get('platform','?')} | Budget: ${j.get('budget',0)}"
                )
            self.send_message("\n".join(lines), markdown=True)
        except Exception as e:
            self.send_message(f"❌ Gagal baca job queue: {e}")

    def _handle_apply(self):
        """Trigger pencarian job sekarang (bypass jadwal)."""
        self.send_message(
            "🔍 Memulai pencarian job sekarang...\n"
            "Agent akan mencari di Upwork, Fiverr, dan Freelancer.com.\n"
            "Hasil akan dikirim via notifikasi."
        )
        # Set flag agar workflow tahu ada manual trigger
        self._manual_apply_trigger = True

    def _handle_test(self):
        """Test koneksi Telegram."""
        if not self.telegram_token:
            self.send_message("❌ TELEGRAM_BOT_TOKEN tidak di-set di .env")
            return
        if not self.chat_id:
            self.send_message("❌ TELEGRAM_CHAT_ID tidak di-set di .env")
            return
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{self.telegram_token}/getMe",
                timeout=10
            )
            if resp.status_code == 200:
                bot_info = resp.json().get("result", {})
                self.send_message(
                    f"✅ *Telegram OK!*\n"
                    f"Bot: @{bot_info.get('username', '?')}\n"
                    f"Chat ID: {self.chat_id}\n"
                    f"Token: ...{self.telegram_token[-6:]}",
                    markdown=True
                )
            else:
                self.send_message(f"❌ Telegram error: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            self.send_message(f"❌ Tidak bisa reach Telegram API: {e}\nCek koneksi internet WSL.")

    def _handle_think(self):
        """Trigger AGI self-reflection on demand."""
        self_improver = getattr(self, 'self_improver', None)
        if not self_improver:
            self.send_message("❌ Self-Improver tidak aktif.")
            return
        try:
            self.send_message("🤔 Menjalankan self-reflection... (30-60 detik)")
            insights = self_improver.reflect(force=True)
            summary = self_improver.get_reflection_summary()
            self.send_message(summary, markdown=True)
        except Exception as e:
            self.send_message(f"❌ Reflection gagal: {e}")

    def _handle_skills(self):
        """Tampilkan statistik skill library."""
        skill_lib = getattr(self, 'skill_library', None)
        if not skill_lib:
            self.send_message("❌ Skill Library tidak aktif.")
            return
        try:
            summary = skill_lib.get_summary_text()
            self.send_message(summary, markdown=True)
        except Exception as e:
            self.send_message(f"❌ Gagal ambil skill stats: {e}")

    # ─────────────────────────────────────────────
    # CONTROL: State check
    # ─────────────────────────────────────────────

    @property
    def is_paused(self) -> bool:
        """Cek apakah agent sedang dijeda oleh user."""
        with self._lock:
            return self._paused
