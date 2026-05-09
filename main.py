"""
main.py — Nexus DualBrain AI
=============================
Workflow utama dengan integrasi OpenClaw:
  1. Crash recovery — lanjutkan task yang terputus dari database.
  2. Shared Resource Setup — Inisialisasi LLM, OpenClaw, Finance, dan Branding.
  3. OpenClaw command listener — user bisa kirim /status /pause /earnings via Telegram.
  4. Inbox check — Tangani negosiasi aktif di Upwork sebelum mulai rotasi.
  5. Freelance Orchestrator — Rotasi Upwork → Fiverr → Freelancer (18/7 loop).
     - Terintegrasi dengan EmailMonitor di background untuk prioritas order.
  6. Code generation via Gemini 2.5 Pro untuk job yang diterima.
  7. Sandbox testing (bwrap) untuk memastikan kode aman dan berfungsi.
  8. Delivery ke klien natively via platform masing-masing.
"""

import gc  # FIX: gc import ditambahkan (sebelumnya hilang → runtime crash)
import time
import logging
import uuid
import os
import psutil
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

# Import modul internal
from database import init_db, save_state, load_state, get_last_incomplete_task
from browser_agent import BrowserAgent
from openclaw_agent import OpenClawAgent        # OpenClaw integration (baru)
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
    """Pause jika RAM > 85% atau CPU > 90% (hardware constraint i3 Gen 8 / 8GB)."""
    while True:
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent(interval=1)
        if ram > 85.0 or cpu > 90.0:
            logging.warning(
                "Hardware kritis (RAM: %.1f%%, CPU: %.1f%%). Pause 60 detik...", ram, cpu
            )
            time.sleep(60)
        else:
            break


# ─────────────────────────────────────────────
# SHARED RESOURCE SETUP
# ─────────────────────────────────────────────

def build_shared_resources():
    """Inisialisasi semua resource yang dipakai bersama antar fase."""
    api_keys = [
        os.environ.get(f"GEMINI_KEY_{i}")
        for i in range(1, 11)
        if os.environ.get(f"GEMINI_KEY_{i}")
    ]
    if not api_keys:
        raise ValueError("CRITICAL: Tidak ada GEMINI_KEY_* di environment. Aborting.")

    llm = GeminiClient(api_keys)

    # OpenClaw agent (menggantikan TelegramAgent biasa)
    # Otomatis fallback ke Telegram direct jika OPENCLAW_API_KEY tidak di-set
    openclaw = OpenClawAgent(gemini_client=llm)

    branding = FreelanceBranding()
    finance  = FinancialTracker()

    branding_strategies = {
        "upwork":     branding.get_branding_strategy("upwork"),
        "fiverr":     branding.get_branding_strategy("fiverr"),
        "freelancer": branding.get_branding_strategy("freelancer"),
    }

    return llm, openclaw, branding_strategies, finance


# ─────────────────────────────────────────────
# FASE: INBOX CHECK
# ─────────────────────────────────────────────

def run_inbox_phase(llm, openclaw: OpenClawAgent, task_id: str) -> tuple:
    """Cek inbox Upwork untuk negosiasi aktif."""
    wait_for_resources()
    save_state(task_id, "RUNNING", "inbox_monitor_phase", {})

    login_success = False
    with BrowserAgent(headless=True) as browser:
        agent = FreelanceAgent(browser, llm)
        login_success = agent.login_upwork()
    gc.collect()

    if not login_success:
        logging.warning("Headless login Upwork gagal. Mencoba headed mode...")
        openclaw.send_message("⚠️ Upwork login gagal. Membutuhkan intervensi manual (Captcha/2FA).")
        with BrowserAgent(headless=False) as browser:
            agent = FreelanceAgent(browser, llm)
            login_success = agent.login_upwork()
        gc.collect()

        if not login_success:
            logging.error("Login Upwork gagal total. Skip inbox check.")
            return "freelance_phase", None

    with BrowserAgent(headless=True) as browser:
        agent = FreelanceAgent(browser, llm)
        state, job_data = agent.check_messages_and_negotiate()
    gc.collect()

    if state == "REVISION_REQUESTED":
        openclaw.send_message(f"🔄 Revisi diminta: {job_data.get('title')}. Regenerating code...")
        return "code_generation_phase", job_data
    elif state == "CONTRACT_ACCEPTED":
        openclaw.send_message(f"🎉 Kontrak diterima: {job_data.get('title')}. Menuju code generation.")
        return "code_generation_phase", job_data
    elif state == "REPLY_ONLY":
        openclaw.send_message("💬 Balasan negosiasi telah dikirim.")

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
        job_data = orchestrator.start()

    gc.collect()
    return job_data


# ─────────────────────────────────────────────
# FASE: CODE GENERATION
# ─────────────────────────────────────────────

def run_code_generation_phase(llm, job_data: dict, task_id: str) -> str | None:
    """Generate Python script menggunakan Gemini 2.5 Pro (model terkuat)."""
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

    logging.info("[CodeGen] Generating code via Gemini 2.5 Pro...")
    # FIX: use_codegen_model=True → pakai Gemini 2.5 Pro, bukan model default
    generated_code = llm.generate_content(prompt, allow_search=True, use_codegen_model=True)
    if not generated_code:
        logging.error("[CodeGen] LLM gagal generate code.")
        return None

    # Bersihkan markdown wrapper jika ada
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
    """Test kode di sandbox aman (bwrap)."""
    wait_for_resources()
    save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})

    sandbox = SandboxTester(duration_minutes=15, llm_client=llm)
    result = sandbox.test_code(code_path)

    if isinstance(result, dict) and result.get("status") == "failed":
        logging.warning("[Sandbox] Testing gagal setelah beberapa kali percobaan.")
        return False
    return bool(result)


# ─────────────────────────────────────────────
# FASE: DELIVERY
# ─────────────────────────────────────────────

def run_delivery_phase(
    llm, openclaw: OpenClawAgent, job_data: dict,
    code_path: str, finance: FinancialTracker, task_id: str
) -> bool:
    """Kirim hasil kerja ke platform yang sesuai."""
    wait_for_resources()

    # Cek apakah ada apology file dari sandbox phase
    state = load_state(task_id)
    apology_file = state.get("data", {}).get("apology_file") if state else None

    if apology_file and os.path.exists(apology_file):
        with open(apology_file, "r") as f:
            apology_message = f.read()
        openclaw.send_message(
            f"⚠️ Gagal menyelesaikan job: {job_data.get('title')}\n"
            f"Platform: {job_data.get('platform', '').upper()}\n\n"
            f"Pesan Pembatalan:\n{apology_message}"
        )
        finance.update_job_status(job_data.get("title"), "CANCELLED")
        return False

    platform = job_data.get("platform", "upwork").lower()
    save_state(task_id, "RUNNING", "delivery_phase", {
        "job_data": job_data, "code_path": code_path
    })

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
        # FIX: Ambil budget dari job_data, bukan hardcode $50
        revenue = float(job_data.get("budget") or job_data.get("rate") or 50.0)
        finance.update_job_status(job_data.get("title"), "DELIVERED", actual_revenue=revenue)
        openclaw.send_message(
            f"✅ SELESAI!\n"
            f"Job: {job_data.get('title')}\n"
            f"Platform: {platform.upper()}\n"
            f"Status: Delivered\n"
            f"Revenue: ${revenue:.2f}"
        )
        return True
    else:
        logging.error(f"Delivery gagal di platform {platform}")
        return False


# ─────────────────────────────────────────────
# WORKFLOW ENGINE
# ─────────────────────────────────────────────

# State global untuk status callback OpenClaw
_workflow_state = {"task_id": None, "current_step": "idle", "start_time": time.time()}


def _get_status():
    """Callback untuk OpenClaw /status command."""
    uptime_secs = int(time.time() - _workflow_state.get("start_time", time.time()))
    hours, rem = divmod(uptime_secs, 3600)
    minutes, _ = divmod(rem, 60)
    return {
        "task_id": _workflow_state.get("task_id", "N/A"),
        "current_step": _workflow_state.get("current_step", "idle"),
        "uptime": f"{hours}j {minutes}m"
    }


def run_workflow(openclaw: OpenClawAgent, finance: FinancialTracker,
                 llm: GeminiClient, branding_strategies: dict):
    """Satu siklus workflow lengkap."""

    # Crash recovery
    last_task = get_last_incomplete_task()
    if last_task:
        task_id     = last_task["task_id"]
        current_step = last_task["current_step"]
        job_data    = last_task.get("data", {}).get("job_data")
        code_path   = last_task.get("data", {}).get("code_path")
        logging.info("♻️ Recovered task %s at step: %s", task_id, current_step)
    else:
        task_id      = str(uuid.uuid4())
        current_step = "inbox_monitor_phase"
        job_data     = None
        code_path    = None

    _workflow_state["task_id"]      = task_id
    _workflow_state["current_step"] = current_step
    save_state(task_id, "STARTED", current_step, {})
    logging.info("🚀 Memulai workflow task %s", task_id)

    try:
        # Cek jika user meminta pause
        if openclaw.is_paused:
            logging.info("[Main] Agent dijeda oleh user. Menunggu /resume...")
            time.sleep(60)
            return SLEEP_DURATION_SHORT

        # Step 0: Inbox check
        if current_step == "inbox_monitor_phase":
            _workflow_state["current_step"] = "inbox_monitor_phase"
            current_step, job_data = run_inbox_phase(llm, openclaw, task_id)

        # Step 1: Freelance loop
        if current_step == "freelance_phase":
            _workflow_state["current_step"] = "freelance_phase"
            job_data = run_freelance_phase(llm, branding_strategies, task_id)
            if job_data:
                current_step = "code_generation_phase"
            else:
                return SLEEP_DURATION_LONG

        # Step 2: Code generation
        if current_step == "code_generation_phase":
            _workflow_state["current_step"] = "code_generation_phase"
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
            _workflow_state["current_step"] = "sandbox_phase"
            if not code_path:
                raise Exception("Path kode tidak ditemukan untuk sandbox.")
            passed = run_sandbox_phase(llm, code_path, task_id)
            if not passed:
                openclaw.send_message("⚠️ Sandbox gagal. Kembali ke fase pencarian job.")
                return SLEEP_DURATION_SHORT
            current_step = "delivery_phase"

        # Step 4: Delivery
        if current_step == "delivery_phase":
            _workflow_state["current_step"] = "delivery_phase"
            if not job_data or not code_path:
                raise Exception("Data tidak lengkap untuk fase delivery.")
            success = run_delivery_phase(llm, openclaw, job_data, code_path, finance, task_id)
            if not success:
                raise Exception("Proses delivery gagal.")

        _workflow_state["current_step"] = "done"
        save_state(task_id, "COMPLETED", "done", {"final_status": "Success"})
        logging.info("✅ Task %s selesai dengan sukses.", task_id)
        return SLEEP_DURATION_SHORT

    except Exception as exc:
        logging.error("❌ Workflow Error: %s", exc)
        save_state(task_id, "FAILED", "error", {"error": str(exc)})
        _workflow_state["current_step"] = "error"
        return SLEEP_DURATION_SHORT


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # FIX: init_db() dipastikan dipanggil di awal (sebelum get_last_incomplete_task)
    init_db()

    logging.info("=" * 60)
    logging.info("Nexus DualBrain AI + OpenClaw — Starting Autonomous Operation")
    logging.info("=" * 60)

    llm, openclaw, branding_strategies, finance = build_shared_resources()
    _workflow_state["start_time"] = time.time()

    # Mulai OpenClaw command listener (background thread)
    openclaw.start_command_listener(
        status_callback=_get_status,
        finance_callback=finance.get_summary
    )

    openclaw.send_message(
        "🚀 Nexus DualBrain AI aktif!\n"
        "Kirim /help untuk melihat perintah yang tersedia.\n"
        "Kirim /status untuk cek kondisi agent."
    )

    try:
        while True:
            try:
                sleep_time = run_workflow(openclaw, finance, llm, branding_strategies)
                logging.info("⏳ Cooldown %d detik...", sleep_time)
                time.sleep(sleep_time)
            except Exception as exc:
                logging.error("💥 Critical Failure: %s", exc)
                openclaw.send_message(f"💥 Critical error: {exc}")
                time.sleep(60)
    finally:
        openclaw.stop_command_listener()
