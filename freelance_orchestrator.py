"""
freelance_orchestrator.py
=========================
Koordinator utama untuk 3 platform freelance: Upwork, Fiverr, Toptal.

Logika:
  - Rotasi platform: Upwork (7 jam) → Fiverr (6 jam) → Toptal (5 jam)
  - EmailMonitor berjalan di background — cek inbox setiap 5 menit
  - Jika ada pesanan masuk dari platform MANAPUN, interupsi slot saat ini
    dan tangani pesanan terlebih dahulu, lalu lanjut sisa slot
  - Jadwal istirahat: 11:00–17:00 WIB (dini hari Amerika, klien sedang tidur)
  - Waktu aktif: 17:00 WIB – 11:00 WIB (09:00–23:00 ET, klien Amerika aktif)
"""

import time
import logging
import threading
import os
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

from email_monitor import EmailMonitor, IncomingOrder
from freelance_agent import FreelanceAgent
from fiverr_agent import FiverrAgent
from toptal_agent import ToptalAgent
from financial_tracker import FinancialTracker

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# TIMEZONE & JADWAL
# ─────────────────────────────────────────────

WIB = timezone(timedelta(hours=7))

# Jam istirahat dalam WIB (dini hari Amerika = sepi klien)
REST_START_WIB = 11   # 11:00 WIB = 23:00 ET — klien Amerika mulai tidur
REST_END_WIB   = 17   # 17:00 WIB = 05:00 ET — mulai aktif lagi

# Durasi slot kerja per platform (dalam detik)
# Total: 7+6+5 = 18 jam aktif per hari
PLATFORM_SLOTS = {
    "upwork": 7 * 3600,    # 7 jam — terbesar, banyak job
    "fiverr": 6 * 3600,    # 6 jam — volume order masuk
    "toptal": 5 * 3600,    # 5 jam — lebih selektif
}

# Rotasi platform (urutan prioritas)
ROTATION_ORDER = ["upwork", "fiverr", "toptal"]

# Interval cek email (sinkron dengan EmailMonitor)
EMAIL_POLL_INTERVAL = int(os.environ.get("EMAIL_CHECK_INTERVAL", 300))


# ─────────────────────────────────────────────
# SCHEDULER UTILITIES
# ─────────────────────────────────────────────

def is_rest_time() -> bool:
    """True jika sekarang jam istirahat (11:00–17:00 WIB)."""
    hour = datetime.now(WIB).hour
    return REST_START_WIB <= hour < REST_END_WIB


def seconds_until_active() -> float:
    """Hitung detik hingga jam aktif berikutnya (17:00 WIB)."""
    now = datetime.now(WIB)
    wake = now.replace(hour=REST_END_WIB, minute=0, second=0, microsecond=0)
    if wake <= now:
        wake += timedelta(days=1)
    return (wake - now).total_seconds()


def wait_until_active():
    """Tunggu sampai jam aktif jika sekarang jam istirahat."""
    if not is_rest_time():
        return
    sleep_sec = seconds_until_active()
    now = datetime.now(WIB)
    logger.info(
        "[Scheduler] 😴 Jam istirahat (%02d:%02d WIB). Tidur %.1f jam hingga 17:00 WIB.",
        now.hour, now.minute, sleep_sec / 3600
    )
    time.sleep(sleep_sec)
    logger.info("[Scheduler] ☀️  Bangun! Waktu aktif dimulai (17:00 WIB).")


# ─────────────────────────────────────────────
# ORCHESTRATOR UTAMA
# ─────────────────────────────────────────────

class FreelanceOrchestrator:
    """
    Mengelola rotasi 3 platform freelance dengan prioritas email.
    Dijalankan dari main.py sebagai loop utama (blocking).
    """

    def __init__(self, browser_agent, llm_client, branding_strategies: dict):
        self.browser = browser_agent
        self.llm = llm_client
        self.branding = branding_strategies
        self.finance = FinancialTracker()

        # Agents per platform
        self._upwork_agent  = FreelanceAgent(browser_agent, llm_client)
        self._fiverr_agent  = FiverrAgent(browser_agent, llm_client)
        self._toptal_agent  = ToptalAgent(browser_agent, llm_client)

        # Email monitor — berjalan di background thread
        self.email_monitor = EmailMonitor()

        # Index platform saat ini dalam rotasi
        self._platform_idx = 0

    def start(self):
        """Entry point — loop tak berujung 18/7."""
        self.email_monitor.start()
        logger.info("[Orchestrator] 🚀 Freelance Agent aktif. Rotasi: %s", " → ".join(ROTATION_ORDER))

        try:
            while True:
                # Patuhi jadwal istirahat sebelum mulai siklus baru
                wait_until_active()

                platform = ROTATION_ORDER[self._platform_idx]
                self._run_platform_slot(platform)

                # Maju ke platform berikutnya
                self._platform_idx = (self._platform_idx + 1) % len(ROTATION_ORDER)

        except KeyboardInterrupt:
            logger.info("[Orchestrator] Dihentikan oleh user.")
        finally:
            self.email_monitor.stop()

    # ─────────────────────────────────────────
    # Slot kerja per platform
    # ─────────────────────────────────────────

    def _run_platform_slot(self, platform: str):
        """
        Jalankan satu slot kerja untuk satu platform.
        Loop internal: setiap EMAIL_POLL_INTERVAL cek apakah ada email prioritas.
        Jika ada → interupsi, handle, lanjut sisa slot.
        Jika jam istirahat tiba → pause sampai aktif lagi.
        """
        slot_seconds = PLATFORM_SLOTS[platform]
        slot_end = time.time() + slot_seconds
        interrupt_event = threading.Event()

        logger.info(
            "[Orchestrator] 🔄 Platform: %s | Slot: %d jam | Mulai: %s WIB",
            platform.upper(),
            slot_seconds // 3600,
            datetime.now(WIB).strftime("%H:%M")
        )

        # Login ke platform saat ini
        self._login_platform(platform)

        # Jalankan job search di thread terpisah
        search_thread = self._start_search_thread(platform, slot_seconds, interrupt_event)

        # Loop monitoring email selama slot masih berlangsung
        while time.time() < slot_end and search_thread.is_alive():
            time.sleep(EMAIL_POLL_INTERVAL)

            # Cek jam istirahat di tengah slot
            if is_rest_time():
                logger.info("[Orchestrator] Jam istirahat tiba. Pause sementara.")
                interrupt_event.set()
                search_thread.join(timeout=30)

                wait_until_active()

                # Resume sisa slot
                remaining = max(0, slot_end - time.time())
                if remaining > 120:
                    logger.info("[Orchestrator] Resume slot %s — sisa %.1f menit.",
                                platform.upper(), remaining / 60)
                    interrupt_event.clear()
                    search_thread = self._start_search_thread(platform, remaining, interrupt_event)
                continue

            # Cek email prioritas
            if self.email_monitor.has_priority_orders():
                self._handle_priority_orders(platform, interrupt_event, search_thread)

                # Resume sisa slot setelah handle pesanan
                remaining = max(0, slot_end - time.time())
                if remaining > 120:
                    logger.info("[Orchestrator] Resume slot %s — sisa %.1f menit.",
                                platform.upper(), remaining / 60)
                    interrupt_event.clear()
                    search_thread = self._start_search_thread(platform, remaining, interrupt_event)

        interrupt_event.set()
        search_thread.join(timeout=30)
        logger.info("[Orchestrator] ✅ Slot %s selesai.", platform.upper())

    def _start_search_thread(self, platform: str, duration: float, interrupt_event: threading.Event) -> threading.Thread:
        """Buat dan start thread job search untuk platform tertentu."""
        t = threading.Thread(
            target=self._search_jobs,
            args=(platform, duration, interrupt_event),
            daemon=True,
            name=f"Search-{platform}"
        )
        t.start()
        return t

    # ─────────────────────────────────────────
    # Job search per platform
    # ─────────────────────────────────────────

    def _search_jobs(self, platform: str, duration: float, stop: threading.Event):
        """
        Aktif cari dan apply job selama `duration` detik.
        Berhenti jika stop di-set.
        """
        start = time.time()
        applied = 0
        branding = self.branding.get(platform, {})

        while (time.time() - start) < duration and not stop.is_set():
            try:
                if platform == "upwork":
                    jobs = self._upwork_agent.scrape_jobs()
                    if jobs:
                        filtered = self._upwork_agent.filter_jobs_batch(jobs)
                        for job in filtered[:2]:
                            if stop.is_set():
                                break
                            success = self._upwork_agent.submit_proposal(job, branding)
                            if success:
                                applied += 1
                                self.finance.log_proposal("upwork", job.get("title"), 50.0)
                            time.sleep(30)

                elif platform == "fiverr":
                    # Di Fiverr, kita cek order aktif + send offers ke buyer requests
                    orders = self._fiverr_agent.check_active_orders()
                    if orders:
                        logger.info("[Fiverr] Ada %d order aktif yang perlu diproses.", len(orders))
                    self._fiverr_agent.search_and_offer_gigs()

                elif platform == "toptal":
                    jobs = self._toptal_agent.check_job_matches()
                    filtered = self._toptal_agent.filter_autonomous_jobs(jobs)
                    for job in filtered[:2]:
                        if stop.is_set():
                            break
                        success = self._toptal_agent.apply_to_job(job, branding)
                        if success:
                            applied += 1
                            self.finance.log_proposal("toptal", job.get("title"), 150.0)
                        time.sleep(45)

                # Jeda antar siklus pencarian (10–15 menit) agar tidak spam
                idle_wait = 0
                while idle_wait < 600 and not stop.is_set():
                    time.sleep(10)
                    idle_wait += 10

            except Exception as exc:
                logger.error("[Search-%s] Error: %s", platform, exc)
                if not stop.is_set():
                    time.sleep(60)

        logger.info("[Search-%s] Selesai. Applied: %d job.", platform.upper(), applied)

    # ─────────────────────────────────────────
    # Handle pesanan prioritas dari email
    # ─────────────────────────────────────────

    def _handle_priority_orders(self, current_platform: str,
                                interrupt_event: threading.Event,
                                search_thread: threading.Thread):
        """
        Hentikan search, tangani semua pesanan prioritas, selesai.
        Pesanan bisa datang dari platform MANAPUN (bukan hanya platform aktif saat ini).
        """
        count = self.email_monitor.pending_count()
        logger.info(
            "[Orchestrator] ⚡ INTERUPSI dari email! %d pesanan menunggu. "
            "Menghentikan slot %s sementara.", count, current_platform.upper()
        )

        interrupt_event.set()
        search_thread.join(timeout=30)

        while self.email_monitor.has_priority_orders():
            order = self.email_monitor.pop_next_order()
            if not order:
                break

            logger.info(
                "[Orchestrator] 🎯 Menangani pesanan dari %s [platform: %s] — %s",
                order.client_name, order.platform.upper(), order.subject
            )

            try:
                self._process_order(order)
            except Exception as exc:
                logger.error("[Orchestrator] Gagal handle pesanan %s: %s", order.order_id, exc)

        logger.info("[Orchestrator] ✅ Semua pesanan email selesai ditangani.")

    def _process_order(self, order: IncomingOrder):
        """
        Proses satu pesanan masuk — generate reply awal, lalu trigger code generation jika perlu.
        """
        branding = self.branding.get(order.platform, {})

        # Generate respons awal ke klien via LLM
        prompt = (
            f"Kamu adalah freelance AI agent. Balas pesan klien berikut secara profesional.\n"
            f"Platform: {order.platform.upper()}\n"
            f"Dari: {order.client_name}\n"
            f"Subject: {order.subject}\n"
            f"Pesan: {order.description}\n\n"
            "Buat balasan singkat (<80 kata) dalam bahasa Inggris. "
            "Konfirmasi kamu menerima pesanan dan akan segera mulai. "
            "Tanyakan satu pertanyaan klarifikasi jika perlu."
        )
        reply = self.llm.generate_content(prompt) if hasattr(self, 'llm') else None

        if order.platform == "upwork":
            # Kirim reply via Upwork messaging
            job_data = {
                "title": order.subject,
                "description": order.description,
                "url": None  # akan navigate ke messages
            }
            if reply:
                logger.info("[Upwork] Reply ke %s: %s", order.client_name, reply[:80])
                # self._upwork_agent.check_messages_and_negotiate() sudah handle reply otomatis

        elif order.platform == "fiverr":
            fake_order = {
                "order_id": order.order_id,
                "buyer_name": order.client_name,
                "title": order.subject,
                "url": None
            }
            if reply:
                self._fiverr_agent.reply_to_buyer(fake_order, reply)

        elif order.platform == "toptal":
            fake_engagement = {
                "job_id": order.order_id,
                "title": order.subject,
                "url": None
            }
            logger.info("[Toptal] Pesanan aktif: %s — siapkan kode.", order.subject)

        # Catat ke financial tracker
        self.finance.log_proposal(order.platform, order.subject, expected_revenue=75.0)
        logger.info("[Orchestrator] Pesanan %s dari %s telah diproses.", order.order_id, order.platform)

    # ─────────────────────────────────────────
    # Login helper
    # ─────────────────────────────────────────

    def _login_platform(self, platform: str):
        """Login ke platform sebelum mulai slot kerja."""
        try:
            if platform == "upwork":
                success = self._upwork_agent.login_upwork()
            elif platform == "fiverr":
                success = self._fiverr_agent.login_fiverr()
            elif platform == "toptal":
                success = self._toptal_agent.login_toptal()
            else:
                success = False

            if success:
                logger.info("[Orchestrator] Login %s berhasil.", platform.upper())
            else:
                logger.warning("[Orchestrator] Login %s GAGAL — slot tetap jalan dengan sesi lama.", platform.upper())
        except Exception as exc:
            logger.warning("[Orchestrator] Error saat login %s: %s", platform, exc)
