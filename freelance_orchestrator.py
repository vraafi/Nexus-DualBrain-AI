"""
freelance_orchestrator.py
=========================
Koordinator utama untuk 3 platform freelance: Upwork, Fiverr, Freelancer.

Logika:
  - Rotasi platform: Upwork (7 jam) → Fiverr (6 jam) → Freelancer (5 jam)
  - EmailMonitor berjalan di background — cek inbox setiap 5 menit
  - Jika ada pesanan masuk dari platform MANAPUN, interupsi slot saat ini
    dan tangani pesanan terlebih dahulu, lalu lanjut sisa slot
  - Jadwal istirahat: 11:00-17:00 WIB (dini hari Amerika, klien sedang tidur)
  - Waktu aktif: 17:00 WIB - 11:00 WIB (09:00-23:00 ET, klien Amerika aktif)

FIX: Syntax error di _process_order() — elif yang salah posisi diperbaiki.
FIX: _login_platform() dipindahkan ke tempat yang benar.
"""

import time
import logging
import threading
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from email_monitor import EmailMonitor, IncomingOrder
from freelance_agent import FreelanceAgent
from fiverr_agent import FiverrAgent
from freelancer_agent import FreelancerAgent
from financial_tracker import FinancialTracker
from circuit_breaker import CircuitBreaker
from error_learning import ErrorLearningSystem
from client_memory import ClientMemory

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

REST_START_WIB = 11
REST_END_WIB   = 17

PLATFORM_SLOTS = {
    "upwork": 7 * 3600,
    "fiverr": 6 * 3600,
    "freelancer": 5 * 3600,
}

ROTATION_ORDER = ["upwork", "fiverr", "freelancer"]
EMAIL_POLL_INTERVAL = int(os.environ.get("EMAIL_CHECK_INTERVAL", 300))


def is_rest_time() -> bool:
    hour = datetime.now(WIB).hour
    return REST_START_WIB <= hour < REST_END_WIB


def seconds_until_active() -> float:
    now = datetime.now(WIB)
    wake = now.replace(hour=REST_END_WIB, minute=0, second=0, microsecond=0)
    if wake <= now:
        wake += timedelta(days=1)
    return (wake - now).total_seconds()


def wait_until_active():
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


class FreelanceOrchestrator:

    def __init__(self, browser_agent, llm_client, branding_strategies: dict):
        self.browser = browser_agent
        self.llm = llm_client
        self.branding = branding_strategies
        self.finance = FinancialTracker()
        self.memory = ClientMemory()

        self._upwork_agent = FreelanceAgent(browser_agent, llm_client)
        self._fiverr_agent = FiverrAgent(browser_agent, llm_client)
        self._freelancer_agent = FreelancerAgent(browser_agent, llm_client)

        self.email_monitor = EmailMonitor()
        self._platform_idx = 0

        # Browser lock — cegah crash akibat concurrent browser access
        self._browser_lock = threading.Lock()

        # Circuit Breaker per platform
        self.circuit_breakers = {
            "upwork": CircuitBreaker("upwork"),
            "fiverr": CircuitBreaker("fiverr"),
            "freelancer": CircuitBreaker("freelancer")
        }

        # Error Learning System
        self.error_learner = ErrorLearningSystem()

    def start(self):
        self.email_monitor.start()
        logger.info("[Orchestrator] 🚀 Freelance Agent aktif. Rotasi: %s", " → ".join(ROTATION_ORDER))

        try:
            while True:
                wait_until_active()
                platform = ROTATION_ORDER[self._platform_idx]
                job_data = self._run_platform_slot(platform)
                if job_data:
                    return job_data
                self._platform_idx = (self._platform_idx + 1) % len(ROTATION_ORDER)
        except KeyboardInterrupt:
            logger.info("[Orchestrator] Dihentikan oleh user.")
        finally:
            self.email_monitor.stop()

    def _login_platform(self, platform: str):
        """Login ke platform yang ditentukan. Dijalankan sekali di awal slot."""
        try:
            with self._browser_lock:
                if platform == "upwork":
                    success = self._upwork_agent.login_upwork()
                elif platform == "fiverr":
                    success = self._fiverr_agent.login_fiverr()
                elif platform == "freelancer":
                    success = self._freelancer_agent.login_freelancer()
                else:
                    success = False

            if success:
                logger.info("[Orchestrator] Login %s berhasil.", platform.upper())
            else:
                logger.warning("[Orchestrator] Login %s GAGAL — lanjut dengan sesi lama.", platform.upper())
        except Exception as exc:
            logger.warning("[Orchestrator] Error login %s: %s", platform, exc)

    def _run_platform_slot(self, platform: str):
        slot_seconds = PLATFORM_SLOTS[platform]
        slot_end = time.time() + slot_seconds
        interrupt_event = threading.Event()

        logger.info(
            "[Orchestrator] 🔄 Platform: %s | Slot: %d jam | Mulai: %s WIB",
            platform.upper(), slot_seconds // 3600,
            datetime.now(WIB).strftime("%H:%M")
        )

        self._login_platform(platform)
        search_thread = self._start_search_thread(platform, slot_seconds, interrupt_event)

        while time.time() < slot_end and search_thread.is_alive():
            time.sleep(EMAIL_POLL_INTERVAL)

            if is_rest_time():
                logger.info("[Orchestrator] Jam istirahat tiba di tengah slot.")
                interrupt_event.set()
                search_thread.join(timeout=30)
                wait_until_active()
                remaining = max(0, slot_end - time.time())
                if remaining > 120:
                    interrupt_event.clear()
                    search_thread = self._start_search_thread(platform, remaining, interrupt_event)
                continue

            if self.email_monitor.has_priority_orders():
                job_data = self._handle_priority_orders(platform, interrupt_event, search_thread)
                if job_data:
                    interrupt_event.set()
                    search_thread.join(timeout=30)
                    return job_data

                remaining = max(0, slot_end - time.time())
                if remaining > 120:
                    logger.info("[Orchestrator] Resume slot %s — sisa %.1f menit.",
                                platform.upper(), remaining / 60)
                    interrupt_event.clear()
                    search_thread = self._start_search_thread(platform, remaining, interrupt_event)

        interrupt_event.set()
        search_thread.join(timeout=30)
        logger.info("[Orchestrator] ✅ Slot %s selesai.", platform.upper())
        return None

    def _start_search_thread(self, platform: str, duration: float, interrupt_event: threading.Event) -> threading.Thread:
        t = threading.Thread(
            target=self._search_jobs,
            args=(platform, duration, interrupt_event),
            daemon=True,
            name=f"Search-{platform}"
        )
        t.start()
        return t

    def _search_jobs(self, platform: str, duration: float, stop: threading.Event):
        """Aktif cari dan apply job selama `duration` detik."""
        start = time.time()
        applied = 0
        branding = self.branding.get(platform, {})

        while (time.time() - start) < duration and not stop.is_set():
            try:
                cb = self.circuit_breakers.get(platform)

                def run_platform_logic():
                    nonlocal applied
                    if platform == "upwork":
                        with self._browser_lock:
                            jobs = self._upwork_agent.scrape_jobs()
                        if jobs:
                            with self._browser_lock:
                                filtered = self._upwork_agent.filter_jobs_batch(jobs)
                            for job in filtered[:2]:
                                if stop.is_set():
                                    break
                                with self._browser_lock:
                                    success = self._upwork_agent.submit_proposal(job, branding)
                                if success:
                                    applied += 1
                                    self.finance.log_proposal("upwork", job.get("title"), 50.0)
                                time.sleep(30)

                    elif platform == "fiverr":
                        with self._browser_lock:
                            orders = self._fiverr_agent.check_active_orders()
                        if orders:
                            logger.info("[Fiverr] %d order aktif ditemukan.", len(orders))
                        with self._browser_lock:
                            self._fiverr_agent.search_and_offer_gigs()

                    elif platform == "freelancer":
                        with self._browser_lock:
                            jobs = self._freelancer_agent.check_job_matches()
                            filtered = self._freelancer_agent.filter_autonomous_jobs(jobs)
                        for job in filtered[:2]:
                            if stop.is_set():
                                break
                            with self._browser_lock:
                                success = self._freelancer_agent.apply_to_job(job, branding)
                            if success:
                                applied += 1
                                self.finance.log_proposal("freelancer", job.get("title"), 150.0)
                            time.sleep(45)

                try:
                    if cb:
                        cb.call(run_platform_logic)
                    else:
                        run_platform_logic()
                except Exception as e:
                    logger.error(f"[Orchestrator] Error for {platform}: {e}")
                    self.error_learner.record_error(platform, type(e).__name__, str(e))
                    time.sleep(60)

                # Jeda 10 menit antar siklus pencarian
                idle_wait = 0
                while idle_wait < 600 and not stop.is_set():
                    time.sleep(10)
                    idle_wait += 10

            except Exception as exc:
                logger.error("[Search-%s] Error: %s", platform, exc)
                if not stop.is_set():
                    time.sleep(60)

        logger.info("[Search-%s] Selesai. Applied: %d job.", platform.upper(), applied)

    def _handle_priority_orders(self, current_platform: str,
                                interrupt_event: threading.Event,
                                search_thread: threading.Thread):
        count = self.email_monitor.pending_count()
        logger.info(
            "[Orchestrator] ⚡ INTERUPSI email! %d pesanan. Hentikan slot %s sementara.",
            count, current_platform.upper()
        )

        # Hentikan search_thread dulu SEBELUM ambil browser_lock (cegah deadlock)
        interrupt_event.set()
        search_thread.join(timeout=30)

        job_data_to_return = None

        while self.email_monitor.has_priority_orders():
            order = self.email_monitor.pop_next_order()
            if not order:
                break
            logger.info(
                "[Orchestrator] 🎯 Handle pesanan: %s [%s] — %s",
                order.client_name, order.platform.upper(), order.subject
            )
            try:
                with self._browser_lock:
                    job_data = self._process_order(order)
                    if job_data and not job_data_to_return:
                        job_data_to_return = job_data
            except Exception as exc:
                logger.error("[Orchestrator] Gagal handle pesanan %s: %s", order.order_id, exc)

        logger.info("[Orchestrator] ✅ Semua pesanan email selesai.")
        return job_data_to_return

    def _process_order(self, order: IncomingOrder):
        """
        Proses satu order dari email. Generate reply dan tentukan state.
        FIXED: Tidak ada lagi syntax error di blok ini.
        """
        # Ambil konteks memori klien
        client_ctx = self.memory.get_context_for_llm(order.platform, order.client_name)

        prompt = (
            f"Kamu adalah freelance AI agent profesional. Balas pesan klien berikut.\n"
            f"Platform: {order.platform.upper()}\n"
            f"Dari: {order.client_name}\n"
            f"Subject: {order.subject}\n"
            f"Pesan: {order.description}\n"
        )
        if client_ctx:
            prompt += f"\nKonteks klien dari riwayat:\n{client_ctx}\n"
        prompt += (
            "\nOutput JSON dengan dua key:\n"
            "1. 'state': satu dari ['REPLY_ONLY', 'REVISION_REQUESTED', 'CONTRACT_ACCEPTED', 'ASK_CLARIFICATION']\n"
            "2. 'reply_text': balasan profesional dalam bahasa Inggris (<80 kata)\n\n"
            "Gunakan CONTRACT_ACCEPTED HANYA jika klien explicitly menyetujui kontrak/order.\n"
            "Gunakan REVISION_REQUESTED HANYA jika klien minta perubahan spesifik pada deliverable."
        )

        # Gunakan negotiation model (26b) untuk analisis pesan
        llm_response = self.llm.generate_content(prompt, require_json=True, use_negotiation_model=True)
        reply = ""
        state = "REPLY_ONLY"

        if llm_response:
            try:
                if "```json" in llm_response:
                    llm_response = llm_response.split("```json")[1].split("```")[0].strip()
                elif "```" in llm_response:
                    llm_response = llm_response.split("```")[1].strip()

                parsed = json.loads(llm_response)
                reply = parsed.get("reply_text", "")
                state = parsed.get("state", "REPLY_ONLY")

            except Exception as e:
                logger.error(f"Failed to parse LLM response: {e}")
                # Fallback: generate reply sederhana
                reply = self.llm.generate_content(
                    f"Write a short professional reply to this freelance client message: {order.description[:200]}. "
                    "Confirm receipt and that you'll start soon. Max 60 words.",
                    use_negotiation_model=True
                ) or "Thank you for your message! I've received your order and will start working on it shortly."
                state = "REPLY_ONLY"
        else:
            reply = "Thank you for your message! I've received your order and will begin shortly."
            state = "REPLY_ONLY"

        # Kirim reply ke platform yang sesuai
        if order.platform == "upwork":
            if reply:
                logger.info("[Upwork] Reply ke %s: %s", order.client_name, reply[:80])

        elif order.platform == "fiverr":
            fake_order = {
                "order_id": order.order_id,
                "buyer_name": order.client_name,
                "title": order.subject,
                "url": None
            }
            if reply:
                self._fiverr_agent.reply_to_buyer(fake_order, reply)

        elif order.platform == "freelancer":
            if reply:
                logger.info("[Freelancer] Reply ke %s: %s", order.client_name, reply[:80])

        # Update memori klien
        self.memory.add_negotiation_note(
            order.platform, order.client_name,
            f"Email order — state: {state} | subject: {order.subject}"
        )
        self.finance.log_proposal(order.platform, order.subject, expected_revenue=75.0)

        logger.info("[Orchestrator] Pesanan %s dari %s selesai diproses. State: %s",
                    order.order_id, order.platform, state)

        # Hanya return job_data jika perlu tindakan lanjut (codegen)
        if state in ["REVISION_REQUESTED", "CONTRACT_ACCEPTED"]:
            return {
                "title": order.subject,
                "description": order.description,
                "platform": order.platform,
                "order_id": order.order_id,
                "client_username": order.client_name,
                "url": ""
            }

        # Untuk REPLY_ONLY dan ASK_CLARIFICATION: tidak perlu codegen
        return None
