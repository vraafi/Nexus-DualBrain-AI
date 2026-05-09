"""
main.py — Nexus DualBrain AI
=============================
Workflow utama:
  1. Crash recovery — lanjutkan task yang terputus dari database.
  2. Shared Resource Setup — Inisialisasi LLM, Telegram, Finance, dan Branding.
  3. Inbox check — Tangani negosiasi aktif di Upwork sebelum mulai rotasi.
  4. Freelance Orchestrator — Rotasi Upwork → Fiverr → Freelancer (18/7 loop).
     - Terintegrasi dengan EmailMonitor di background untuk prioritas order.
  5. Code generation via Gemini API untuk job yang diterima.
  6. Sandbox testing (bwrap) untuk memastikan kode aman dan berfungsi.
  7. Delivery ke klien natively via platform masing-masing.
"""

import time
import logging
import gc
import uuid
import os
import psutil
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

# Import modul internal
from database import init_db, save_state, load_state, get_last_incomplete_task
from browser_agent import BrowserAgent
from telegram_agent import TelegramAgent
from freelance_agent import FreelanceAgent
from fiverr_agent import FiverrAgent
from freelancer_agent import FreelancerAgent
from freelance_branding import FreelanceBranding
from freelance_orchestrator import FreelanceOrchestrator
from sandbox_tester import SandboxTester
from api_client import GeminiClient
from financial_tracker import FinancialTracker

load_dotenv()

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
# KONSTANTA & RESOURCE GUARD
# ─────────────────────────────────────────────

SLEEP_DURATION_LONG  = 7200   # 2 jam — jika tidak ada job ditemukan
SLEEP_DURATION_SHORT = 1800   # 30 menit — setelah menyelesaikan job

def wait_for_resources():
    """Pause jika RAM > 85% atau CPU > 90% (hardware constraint)."""
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
        "freelancer": branding.get_branding_strategy("freelancer"),
    }

    return llm, telegram, branding_strategies, finance

# ─────────────────────────────────────────────
# FASE: INBOX CHECK
# ─────────────────────────────────────────────

def run_inbox_phase(llm, telegram, task_id: str) -> tuple[str, dict | None]:
    """Cek inbox Upwork untuk negosiasi aktif."""
    wait_for_resources()
    save_state(task_id, "RUNNING", "inbox_monitor_phase", {})

    login_success = False
    # Coba login Upwork
    with BrowserAgent(headless=True) as browser:
        agent = FreelanceAgent(browser, llm)
        login_success = agent.login_upwork()

    if not login_success:
        logging.warning("Headless login Upwork gagal. Mencoba headed mode...")
        telegram.send_message("⚠️ Upwork login gagal. Membutuhkan intervensi manual (Captcha/2FA).")
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
        telegram.send_message(f"🔄 Revisi diminta: {job_data.get('title')}. Regenerating code...")
        return "code_generation_phase", job_data
    elif state == "CONTRACT_ACCEPTED":
        telegram.send_message(f"🎉 Kontrak diterima: {job_data.get('title')}. Menuju code generation.")
        return "code_generation_phase", job_data
    elif state == "REPLY_ONLY":
        telegram.send_message("💬 Balasan negosiasi telah dikirim.")

    return "freelance_phase", None

# ─────────────────────────────────────────────
# FASE: FREELANCE ORCHESTRATOR
# ─────────────────────────────────────────────

def run_freelance_phase(llm, branding_strategies: dict, task_id: str):
    """Loop rotasi platform via Orchestrator."""
    wait_for_resources()
    save_state(task_id, "RUNNING", "freelance_phase", {})
    logging.info("[Main] Memulai FreelanceOrchestrator (18/7 loop)...")

    with BrowserAgent(headless=True) as browser:
        orchestrator = FreelanceOrchestrator(
            browser_agent=browser,
            llm_client=llm,
            branding_strategies=branding_strategies,
        )
        # orchestrator.start() akan mengelola EmailMonitor dan rotasi platform
        job_data = orchestrator.start() 

    gc.collect()
    return job_data

# ─────────────────────────────────────────────
# FASE: CODE GENERATION
# ─────────────────────────────────────────────

def run_code_generation_phase(llm, job_data: dict, task_id: str) -> str | None:
    """Generate Python script menggunakan Gemini API."""
    wait_for_resources()
    save_state(task_id, "RUNNING", "code_generation_phase", {"job_data": job_data})

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    code_path = f"generated_script_{timestamp_str}_{task_id[:8]}.py"

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

    # Clean markdown
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
    """Test kode di sandbox aman."""
    wait_for_resources()
    save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})

    sandbox = SandboxTester(duration_minutes=15, llm_client=llm)
    result = sandbox.test_code(code_path)

    if isinstance(result, dict) and result.get("status") == "failed":
        logging.warning("[Sandbox] Failsafe: Testing gagal setelah beberapa kali percobaan.")
        return False
    return bool(result)

# ─────────────────────────────────────────────
# FASE: DELIVERY
# ─────────────────────────────────────────────

def run_delivery_phase(llm, telegram, job_data: dict, code_path: str, finance: FinancialTracker, task_id: str):
    """Kirim hasil kerja ke platform yang sesuai."""
    wait_for_resources()
    platform = job_data.get("platform", "upwork").lower()
    save_state(task_id, "RUNNING", "delivery_phase", {"job_data": job_data, "code_path": code_path})

    delivered = False
    with BrowserAgent(headless=True) as browser:
        if platform == "upwork":
            agent = FreelanceAgent(browser, llm)
            delivered = agent.deliver_work(job_data, code_path)
        elif platform == "fiverr":
            agent = FiverrAgent(browser, llm)
            delivery_msg = "Here is the completed code. Let me know if you need any changes."
            delivered = agent.deliver_order(job_data, code_path, delivery_msg)
        elif platform == "freelancer":
            agent = FreelancerAgent(browser, llm)
            delivered = agent.deliver_work(job_data, code_path)
        
        gc.collect()

    if delivered:
        revenue = 50.0 # Default estimate
        finance.update_job_status(job_data.get("title"), "DELIVERED", actual_revenue=revenue)
        telegram.send_message(
            f"🎉 SELESAI!\nJob: {job_data.get('title')}\nPlatform: {platform.upper()}\nStatus: Delivered\nRevenue: ${revenue}"
        )
        return True
    else:
        logging.error(f"Delivery gagal di platform {platform}")
        return False

# ─────────────────────────────────────────────
# WORKFLOW ENGINE
# ─────────────────────────────────────────────

def run_workflow():
    llm, telegram, branding_strategies, finance = build_shared_resources()

    # Crash recovery
    last_task = get_last_incomplete_task()
    if last_task:
        task_id = last_task["task_id"]
        current_step = last_task["current_step"]
        job_data = last_task.get("data", {}).get("job_data")
        code_path = last_task.get("data", {}).get("code_path")
        logging.info("♻️ Recovered task %s at step: %s", task_id, current_step)
    else:
        task_id = str(uuid.uuid4())
        current_step = "inbox_monitor_phase"
        job_data = None
        code_path = None

    save_state(task_id, "STARTED", current_step, {})
    logging.info("🚀 Memulai workflow task %s", task_id)

    try:
        # Step 0: Inbox check
        if current_step == "inbox_monitor_phase":
            current_step, job_data = run_inbox_phase(llm, telegram, task_id)

        # Step 1: Freelance loop (pencarian job)
        if current_step == "freelance_phase":
            job_data = run_freelance_phase(llm, branding_strategies, task_id)
            if job_data:
                current_step = "code_generation_phase"
            else:
                return SLEEP_DURATION_SHORT

        # Step 2: Code generation
        if current_step == "code_generation_phase":
            if not job_data:
                state = load_state(task_id)
                job_data = state.get("data", {}).get("job_data") if state else None
            
            if not job_data:
                raise Exception("Data job hilang. Tidak bisa lanjut ke CodeGen.")
            
            code_path = run_code_generation_phase(llm, job_data, task_id)
            if not code_path:
                raise Exception("Code generation gagal.")
            current_step = "sandbox_phase"

        # Step 3: Sandbox test
        if current_step == "sandbox_phase":
            if not code_path:
                raise Exception("Path kode tidak ditemukan untuk sandbox.")
            
            passed = run_sandbox_phase(llm, code_path, task_id)
            if not passed:
                telegram.send_message("⚠️ Sandbox gagal. Kembali ke fase pencarian job.")
                return SLEEP_DURATION_SHORT
            current_step = "delivery_phase"

        # Step 4: Delivery
        if current_step == "delivery_phase":
            if not job_data or not code_path:
                raise Exception("Data tidak lengkap untuk fase delivery.")
            
            success = run_delivery_phase(llm, telegram, job_data, code_path, finance, task_id)
            if not success:
                raise Exception("Proses delivery gagal.")

        save_state(task_id, "COMPLETED", "done", {"final_status": "Success"})
        logging.info("✅ Task %s selesai dengan sukses.", task_id)
        return SLEEP_DURATION_SHORT

    except Exception as exc:
        logging.error("❌ Workflow Error: %s", exc)
        save_state(task_id, "FAILED", "error", {"error": str(exc)})
        return SLEEP_DURATION_SHORT

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    logging.info("=" * 60)
    logging.info("Nexus DualBrain AI — Starting Autonomous Operation")
    logging.info("=" * 60)

    while True:
        try:
            sleep_time = run_workflow()
            logging.info("⏳ Cooldown %d detik...", sleep_time)
            time.sleep(sleep_time)
        except Exception as exc:
            logging.error("💥 Critical Failure: %s", exc)
            time.sleep(60)
