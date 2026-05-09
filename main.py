"""
main.py — Nexus DualBrain AI
=============================
Workflow utama (tanpa Veo 3):
  1. Crash recovery — lanjutkan task yang terputus
  2. Inbox check — tangani negosiasi aktif terlebih dulu
  3. Freelance Orchestrator — rotasi Upwork → Fiverr → Toptal (18/7)
     dengan EmailMonitor di background untuk prioritas email masuk
  4. Code generation via Gemini API + Sandbox testing (bwrap)
  5. Delivery ke klien natively via platform
"""

import time
import logging
import gc
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

from database import init_db, save_state, load_state, get_last_incomplete_task
from browser_agent import BrowserAgent
from telegram_agent import TelegramAgent
from freelance_agent import FreelanceAgent
from freelance_branding import FreelanceBranding
from freelance_orchestrator import FreelanceOrchestrator
from sandbox_tester import SandboxTester
from api_client import GeminiClient
from financial_tracker import FinancialTracker
import psutil

from logging.handlers import RotatingFileHandler

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────

log_formatter = logging.Formatter("%(asctime)s [%(threadName)s] %(levelname)s — %(message)s")
log_file = "agent_activity.log"
file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2)
file_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

# ─────────────────────────────────────────────
# KONSTANTA
# ─────────────────────────────────────────────

SLEEP_DURATION_LONG  = 7200   # 2 jam — jika tidak ada job ditemukan
SLEEP_DURATION_SHORT = 1800   # 30 menit — setelah menyelesaikan job


# ─────────────────────────────────────────────
# RESOURCE GUARD
# ─────────────────────────────────────────────

def wait_for_resources():
    """Pause jika RAM > 85% atau CPU > 90% (hardware constraint i3 Gen8, 8GB RAM)."""
    while True:
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent(interval=1)
        if ram > 85.0 or cpu > 90.0:
            logging.warning("Hardware kritis (RAM: %.1f%%, CPU: %.1f%%). Pause 60 detik...", ram, cpu)
            time.sleep(60)
        else:
            break


# ─────────────────────────────────────────────
# SHARED RESOURCE SETUP
# ─────────────────────────────────────────────

def build_shared_resources():
    """Inisialisasi semua resource yang dipakai bersama antar fase."""
    api_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11) if os.environ.get(f"GEMINI_KEY_{i}")]
    if not api_keys:
        raise ValueError("CRITICAL: Tidak ada GEMINI_KEY_* di environment. Aborting.")

    llm = GeminiClient(api_keys)

    telegram_token   = os.environ.get("TELEGRAM_BOT_TOKEN", "mock_token")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "mock_chat_id")
    if telegram_token == "mock_token":
        logging.warning("TELEGRAM_BOT_TOKEN tidak di-set. Notifikasi Telegram non-aktif.")

    telegram = TelegramAgent(telegram_token, telegram_chat_id)
    branding = FreelanceBranding()
    finance  = FinancialTracker()

    branding_strategies = {
        "upwork": branding.get_branding_strategy("upwork"),
        "fiverr": branding.get_branding_strategy("fiverr"),
        "toptal": branding.get_branding_strategy("toptal"),
    }

    return llm, telegram, branding_strategies, finance


# ─────────────────────────────────────────────
# FASE: INBOX CHECK (negosiasi aktif)
# ─────────────────────────────────────────────

def run_inbox_phase(llm, telegram, task_id: str) -> tuple[str, dict | None]:
    """
    Cek inbox Upwork sebelum mulai rotasi — tangani negosiasi aktif.
    Return (next_step, job_data_jika_ada)
    """
    wait_for_resources()
    save_state(task_id, "RUNNING", "inbox_monitor_phase", {})

    # Login (coba headless dulu, fallback headed jika gagal)
    login_success = False
    with BrowserAgent(headless=True) as browser:
        agent = FreelanceAgent(browser, llm)
        login_success = agent.login_upwork()

    if not login_success:
        logging.warning("Headless login Upwork gagal. Mencoba headed mode untuk manual intervention...")
        telegram.send_message("⚠️ Upwork login gagal. Buka browser untuk captcha/2FA.")
        with BrowserAgent(headless=False) as browser:
            agent = FreelanceAgent(browser, llm)
            login_success = agent.login_upwork()
        if not login_success:
            logging.error("Login Upwork gagal total. Skip inbox check.")
            return "freelance_phase", None

    with BrowserAgent(headless=True) as browser:
        agent = FreelanceAgent(browser, llm)
        state, job_data = agent.check_messages_and_negotiate()
        gc.collect()

    if state == "REVISION_REQUESTED":
        telegram.send_message(f"🔄 Revisi diminta: {job_data['title']}. Regenerating code...")
        return "code_generation_phase", job_data
    elif state == "CONTRACT_ACCEPTED":
        telegram.send_message("🎉 Kontrak diterima! Menuju delivery.")
        return "delivery_phase", job_data
    elif state == "REPLY_ONLY":
        telegram.send_message("💬 Reply negosiasi terkirim.")

    return "freelance_phase", None


# ─────────────────────────────────────────────
# FASE: FREELANCE ORCHESTRATOR (loop utama)
# ─────────────────────────────────────────────

def run_freelance_phase(llm, branding_strategies: dict, task_id: str):
    """
    Loop utama 18/7: rotasi Upwork → Fiverr → Toptal.
    EmailMonitor berjalan di background — interupsi otomatis jika ada pesanan.
    Blocking — tidak akan return kecuali ada exception.
    """
    wait_for_resources()
    save_state(task_id, "RUNNING", "freelance_phase", {})
    logging.info("[Main] Memulai FreelanceOrchestrator (18/7 loop)...")

    with BrowserAgent(headless=True) as browser:
        orchestrator = FreelanceOrchestrator(
            browser_agent=browser,
            llm_client=llm,
            branding_strategies=branding_strategies,
        )
        orchestrator.start()  # Blocking 18/7

    gc.collect()


# ─────────────────────────────────────────────
# FASE: CODE GENERATION
# ─────────────────────────────────────────────

def run_code_generation_phase(llm, job_data: dict, task_id: str) -> str | None:
    """
    Generate kode Python untuk job yang diterima menggunakan Gemini API.
    Return path file kode yang dihasilkan, atau None jika gagal.
    """
    wait_for_resources()
    save_state(task_id, "RUNNING", "code_generation_phase", {"job_data": job_data})

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    code_path = f"generated_script_{timestamp_str}_{task_id[:8]}.py"

    # Bersihkan script lama (> 7 hari)
    try:
        for f in os.listdir("."):
            if f.startswith("generated_script_") and f.endswith(".py"):
                if time.time() - os.path.getmtime(f) > 7 * 86400:
                    os.remove(f)
    except Exception:
        pass

    prompt = (
        f"Act as a senior backend Python developer. I have accepted the following freelance job:\n"
        f"Title: {job_data.get('title')}\n"
        f"Description: {job_data.get('description')}\n"
        "Write the complete, robust Python script to solve this task. "
        "Include relevant unit tests at the bottom using the built-in `unittest` module. "
        "Output ONLY valid Python code. Do not wrap in markdown or explain."
    )

    logging.info("[CodeGen] Generating code via Gemini API...")
    generated_code = llm.generate_content(prompt, allow_search=True)
    if not generated_code:
        logging.error("[CodeGen] LLM gagal generate code.")
        return None

    # Strip markdown jika LLM tidak patuh
    if "```python" in generated_code:
        generated_code = generated_code.split("```python")[1].split("```")[0].strip()
    elif "```" in generated_code:
        generated_code = generated_code.split("```")[1].strip()

    with open(code_path, "w") as f:
        f.write(generated_code)

    logging.info("[CodeGen] Code tersimpan ke: %s", code_path)
    return code_path


# ─────────────────────────────────────────────
# FASE: SANDBOX TEST
# ─────────────────────────────────────────────

def run_sandbox_phase(llm, code_path: str, task_id: str) -> bool:
    """
    Test kode di sandbox bwrap. Return True jika berhasil, False jika gagal total.
    """
    wait_for_resources()
    save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})

    sandbox = SandboxTester(duration_minutes=15, llm_client=llm)
    result = sandbox.test_code(code_path)

    if isinstance(result, dict) and result.get("status") == "failed":
        logging.warning("[Sandbox] Failsafe diaktifkan setelah 7 retry.")
        return False
    return bool(result)


# ─────────────────────────────────────────────
# FASE: PROPOSAL + DELIVERY
# ─────────────────────────────────────────────

def run_proposal_and_delivery_phase(llm, telegram, job_data: dict,
                                    code_path: str, finance: FinancialTracker,
                                    task_id: str):
    """Submit proposal, tunggu kontrak, deliver hasil kerja."""
    wait_for_resources()
    branding = FreelanceBranding()
    brand_ctx = branding.get_branding_strategy("upwork")

    # Submit proposal
    save_state(task_id, "RUNNING", "proposal_phase", {"job_data": job_data})
    finance.log_proposal("upwork", job_data.get("title", "Unknown"), expected_revenue=50.0)

    with BrowserAgent(headless=True) as browser:
        agent = FreelanceAgent(browser, llm)
        proposal_ok = agent.submit_proposal(job_data, brand_ctx, code_path)
        gc.collect()

    if not proposal_ok:
        telegram.send_message("❌ Gagal submit proposal.")
        raise Exception("Proposal submission failed.")

    telegram.send_message(f"✅ Proposal terkirim: {job_data.get('title')}")

    # Delivery
    save_state(task_id, "RUNNING", "delivery_phase", {"job_data": job_data})
    with BrowserAgent(headless=True) as browser:
        agent = FreelanceAgent(browser, llm)
        delivered = agent.deliver_work(job_data, code_path)
        gc.collect()

    if delivered:
        finance.update_job_status(job_data.get("title"), "DELIVERED", actual_revenue=50.0)
        telegram.send_message(
            f"🎉 SELESAI!\nJob: {job_data.get('title')}\nStatus: Delivered\nRevenue: $50.00"
        )
    else:
        raise Exception("Delivery gagal.")


# ─────────────────────────────────────────────
# MAIN WORKFLOW
# ─────────────────────────────────────────────

def run_workflow():
    llm, telegram, branding_strategies, finance = build_shared_resources()

    # Crash recovery
    last_task = get_last_incomplete_task()
    if last_task:
        task_id = last_task["task_id"]
        current_step = last_task["current_step"]
        job_data = last_task.get("data", {}).get("job_data")
        logging.info("♻️  Recovered task %s at step: %s", task_id, current_step)
    else:
        task_id = str(uuid.uuid4())
        current_step = "inbox_monitor_phase"
        job_data = None

    save_state(task_id, "STARTED", current_step, {})
    logging.info("🚀 Memulai workflow task %s", task_id)

    try:
        code_path = None

        # ── Step 0: Inbox check ──────────────────────
        if current_step in ["init", "inbox_monitor_phase"]:
            current_step, job_data = run_inbox_phase(llm, telegram, task_id)

        # ── Step 1: Freelance 18/7 loop ──────────────
        if current_step == "freelance_phase":
            # Loop ini blocking — tidak akan lanjut ke step berikutnya kecuali crash
            run_freelance_phase(llm, branding_strategies, task_id)
            return SLEEP_DURATION_SHORT  # Jika entah bagaimana keluar dari loop

        # ── Step 2: Code generation ──────────────────
        if current_step == "code_generation_phase":
            if not job_data:
                state = load_state(task_id)
                job_data = state.get("data", {}).get("job_data") if state else None
            if not job_data:
                raise Exception("Job data hilang. Tidak bisa generate code.")
            code_path = run_code_generation_phase(llm, job_data, task_id)
            if not code_path:
                raise Exception("Code generation gagal.")
            current_step = "sandbox_phase"

        # ── Step 3: Sandbox test ─────────────────────
        if current_step == "sandbox_phase":
            if not code_path:
                raise Exception("code_path tidak tersedia untuk sandbox.")
            passed = run_sandbox_phase(llm, code_path, task_id)
            if not passed:
                telegram.send_message("⚠️ Sandbox gagal setelah 7 retry. Kembali ke job hunt.")
                return SLEEP_DURATION_SHORT
            current_step = "proposal_phase"

        # ── Step 4: Proposal + Delivery ──────────────
        if current_step in ["proposal_phase", "delivery_phase"]:
            if not job_data or not code_path:
                raise Exception("Data hilang untuk proposal/delivery.")
            run_proposal_and_delivery_phase(llm, telegram, job_data, code_path, finance, task_id)

        save_state(task_id, "COMPLETED", "done", {"final_status": "Success"})
        logging.info("✅ Task %s selesai.", task_id)
        with open("completion_report.log", "a") as f:
            f.write(f"Task {task_id} finished at {time.ctime()}.\n")
        return SLEEP_DURATION_SHORT

    except Exception as exc:
        logging.error("❌ Workflow gagal: %s", exc)
        save_state(task_id, "FAILED", "error", {"error": str(exc)})
        if "No fully autonomous jobs found" in str(exc) or "No jobs found" in str(exc):
            return SLEEP_DURATION_LONG
        return SLEEP_DURATION_SHORT


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    logging.info("=" * 60)
    logging.info("Nexus DualBrain AI — Starting 18/7 Operation")
    logging.info("Platforms: Upwork (7h) → Fiverr (6h) → Toptal (5h)")
    logging.info("Rest: 11:00–17:00 WIB | Active: 17:00–11:00 WIB")
    logging.info("=" * 60)

    while True:
        try:
            sleep_time = run_workflow()
            logging.info("⏳ Cooldown %d detik sebelum siklus berikutnya...", sleep_time)
            time.sleep(sleep_time)
        except Exception as exc:
            logging.error("💥 Critical outer loop failure: %s", exc)
            time.sleep(60)
