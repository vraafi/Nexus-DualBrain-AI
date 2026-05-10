"""
main.py — Nexus DualBrain AI (OpenClaw Orchestrated)
======================================================
CATATAN: Dengan integrasi OpenClaw penuh, main.py ini sekarang berperan
sebagai FALLBACK runner jika OpenClaw belum/tidak terinstall.

Cara menjalankan DENGAN OpenClaw (DIREKOMENDASIKAN):
  1. npm install -g openclaw@latest
  2. openclaw onboard --install-daemon
  3. openclaw start --config .openclaw/openclaw.json

Cara menjalankan TANPA OpenClaw (fallback Python loop):
  python main.py

OpenClaw akan otomatis:
  - Mengorkestrasi semua SKILL di .openclaw/skills/
  - Handle scheduling (jam istirahat WIB)
  - Handle memori klien
  - Handle browser via CDP Extension Relay
  - Koneksi Telegram untuk kontrol
"""

import gc
import time
import logging
import uuid
import os
import psutil
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

from database import init_db, save_state, load_state, get_last_incomplete_task
from browser_agent import BrowserAgent
from freelance_agent import FreelanceAgent
from fiverr_agent import FiverrAgent
from freelancer_agent import FreelancerAgent
from freelance_branding import FreelanceBranding
from freelance_orchestrator import FreelanceOrchestrator
from sandbox_tester import SandboxTester
from api_client import GeminiClient
from financial_tracker import FinancialTracker
from openclaw_agent import OpenClawAgent

    load_dotenv()

    RESIDENTIAL_PROXIES_STR = os.environ.get("RESIDENTIAL_PROXIES", "")
    RESIDENTIAL_PROXIES = [p.strip() for p in RESIDENTIAL_PROXIES_STR.split(",") if p.strip()]


# ─── LOGGING ───
log_formatter = logging.Formatter("%(asctime)s [%(threadName)s] %(levelname)s — %(message)s")
file_handler = RotatingFileHandler("agent_activity.log", maxBytes=5*1024*1024, backupCount=2)
file_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

SLEEP_DURATION_LONG  = 7200
SLEEP_DURATION_SHORT = 1800


def wait_for_resources():
    while True:
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent(interval=1)
        if ram > 85.0 or cpu > 90.0:
            logging.warning("Hardware kritis (RAM: %.1f%%, CPU: %.1f%%). Pause 60s...", ram, cpu)
            time.sleep(60)
        else:
            break


current_proxy_index = 0
def get_next_proxy(proxies):
    global current_proxy_index
    if not proxies:
        return None
    proxy = proxies[current_proxy_index]
    current_proxy_index = (current_proxy_index + 1) % len(proxies)
    return proxy

def build_shared_resources():
    api_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
                if os.environ.get(f"GEMINI_KEY_{i}")]
    if not api_keys:
        raise ValueError("CRITICAL: Tidak ada GEMINI_KEY_* di environment.")

    llm      = GeminiClient(api_keys)
    openclaw = OpenClawAgent(gemini_client=llm)
    branding = FreelanceBranding()
    finance  = FinancialTracker()

    branding_strategies = {
        p: branding.get_branding_strategy(p)
        for p in ["upwork", "fiverr", "freelancer"]
    }
    return llm, openclaw, branding_strategies, finance


_workflow_state = {"task_id": None, "current_step": "idle", "start_time": time.time()}


def _get_status():
    uptime = int(time.time() - _workflow_state.get("start_time", time.time()))
    h, rem = divmod(uptime, 3600)
    m, _ = divmod(rem, 60)
    return {
        "task_id": _workflow_state.get("task_id", "N/A"),
        "current_step": _workflow_state.get("current_step", "idle"),
        "uptime": f"{h}j {m}m",
        "mode": "Python fallback (OpenClaw tidak aktif)"
    }


def run_workflow(openclaw, finance, llm, branding_strategies):
    last_task = get_last_incomplete_task()
    if last_task:
        task_id      = last_task["task_id"]
        current_step = last_task["current_step"]
        job_data     = last_task.get("data", {}).get("job_data")
        code_path    = last_task.get("data", {}).get("code_path")
        logging.info("♻️ Recovered task %s at step: %s", task_id, current_step)
    else:
        task_id      = str(uuid.uuid4())
        current_step = "inbox_monitor_phase"
        job_data     = None
        code_path    = None

    _workflow_state.update({"task_id": task_id, "current_step": current_step})
    save_state(task_id, "STARTED", current_step, {})

    if openclaw.is_paused:
        logging.info("Agent dijeda. Menunggu /resume...")
        time.sleep(60)
        return SLEEP_DURATION_SHORT

    try:
        if current_step == "inbox_monitor_phase":
            _workflow_state["current_step"] = "inbox_monitor_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "inbox_monitor_phase", {})
            current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
            with BrowserAgent(headless=True, proxy=current_proxy) as browser:
                agent = FreelanceAgent(browser, llm)
                login_ok = agent.login_upwork()
            gc.collect()
            if login_ok:
                current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
                with BrowserAgent(headless=True, proxy=current_proxy) as browser:
                    agent = FreelanceAgent(browser, llm)
                    state, job_data = agent.check_messages_and_negotiate()
                gc.collect()
                if state in ("REVISION_REQUESTED", "CONTRACT_ACCEPTED"):
                    current_step = "code_generation_phase"
                else:
                    current_step = "freelance_phase"
            else:
                openclaw.send_message("⚠️ Upwork login gagal — perlu intervensi manual.")
                current_step = "freelance_phase"

        if current_step == "freelance_phase":
            _workflow_state["current_step"] = "freelance_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "freelance_phase", {})
            current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
            with BrowserAgent(headless=True, proxy=current_proxy) as browser:
                orchestrator = FreelanceOrchestrator(
                    browser_agent=browser, llm_client=llm,
                    branding_strategies=branding_strategies
                )
                job_data = orchestrator.start()
            gc.collect()
            if job_data:
                current_step = "code_generation_phase"
            else:
                return SLEEP_DURATION_LONG

        if current_step == "code_generation_phase":
            _workflow_state["current_step"] = "code_generation_phase"
            wait_for_resources()
            if not job_data:
                state = load_state(task_id)
                job_data = (state or {}).get("data", {}).get("job_data")
            if not job_data:
                raise Exception("Data job hilang.")

            save_state(task_id, "RUNNING", "code_generation_phase", {"job_data": job_data})
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            code_path = f"generated_script_{timestamp}_{task_id[:8]}.py"
            prompt = (
                f"Act as a senior Python developer.\n"
                f"Title: {job_data.get('title')}\n"
                f"Description: {job_data.get('description')}\n"
                "Write complete, production-ready Python code with unit tests. "
                "Output ONLY valid Python code."
            )
            code = llm.generate_content(prompt, allow_search=True, use_codegen_model=True)
            if not code:
                raise Exception("Code generation gagal.")
            for marker in ("```python", "```"):
                if marker in code:
                    code = code.split(marker)[1].split("```")[0].strip()
                    break
            with open(code_path, "w") as f:
                f.write(code)
            current_step = "sandbox_phase"

        if current_step == "sandbox_phase":
            _workflow_state["current_step"] = "sandbox_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})
            sandbox = SandboxTester(duration_minutes=15, llm_client=llm)
            passed = bool(sandbox.test_code(code_path))
            if not passed:
                openclaw.send_message("⚠️ Sandbox gagal. Kembali ke fase pencarian job.")
                return SLEEP_DURATION_SHORT
            current_step = "delivery_phase"

        if current_step == "delivery_phase":
            _workflow_state["current_step"] = "delivery_phase"
            wait_for_resources()
            if not job_data or not code_path:
                raise Exception("Data tidak lengkap untuk delivery.")
            platform = job_data.get("platform", "upwork").lower()
            save_state(task_id, "RUNNING", "delivery_phase",
                       {"job_data": job_data, "code_path": code_path})
            delivered = False
            current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
            with BrowserAgent(headless=True, proxy=current_proxy) as browser:
                if platform == "upwork":
                    agent = FreelanceAgent(browser, llm)
                    delivered = agent.deliver_work(job_data, code_path)
                elif platform == "fiverr":
                    agent = FiverrAgent(browser, llm)
                    delivered = agent.deliver_order(
                        job_data, code_path,
                        "Here is the completed code. Let me know if you need changes."
                    )
                elif platform == "freelancer":
                    agent = FreelancerAgent(browser, llm)
                    delivered = agent.deliver_work(job_data, code_path)
            gc.collect()
            if delivered:
                revenue = float(job_data.get("budget") or job_data.get("rate") or 50.0)
                finance.update_job_status(job_data.get("title"), "DELIVERED", revenue)
                openclaw.send_message(
                    f"✅ DELIVERED!\nJob: {job_data.get('title')}\n"
                    f"Platform: {platform.upper()}\nRevenue: ${revenue:.2f}"
                )

        _workflow_state["current_step"] = "done"
        save_state(task_id, "COMPLETED", "done", {})
        logging.info("✅ Task %s selesai.", task_id)
        return SLEEP_DURATION_SHORT

    except Exception as exc:
        logging.error("❌ Workflow Error: %s", exc)
        save_state(task_id, "FAILED", "error", {"error": str(exc)})
        _workflow_state["current_step"] = "error"
        return SLEEP_DURATION_SHORT


if __name__ == "__main__":
    init_db()
    logging.info("=" * 60)
    logging.info("Nexus DualBrain AI — Python Fallback Mode")
    logging.info("REKOMENDASI: Gunakan OpenClaw untuk orkestrasi penuh")
    logging.info("  npm install -g openclaw@latest")
    logging.info("  openclaw start --config .openclaw/openclaw.json")
    logging.info("=" * 60)

    llm, openclaw, branding_strategies, finance = build_shared_resources()
    _workflow_state["start_time"] = time.time()

    openclaw.start_command_listener(
        status_callback=_get_status,
        finance_callback=finance.get_summary
    )
    openclaw.send_message(
        "🚀 Nexus DualBrain AI aktif (Python fallback mode).\n"
        "Untuk fitur penuh, install OpenClaw: npm install -g openclaw@latest\n"
        "Kirim /help untuk daftar perintah."
    )

    try:
        while True:
            try:
                sleep_time = run_workflow(openclaw, finance, llm, branding_strategies)
                logging.info("⏳ Cooldown %d detik...", sleep_time)
                time.sleep(sleep_time)
            except Exception as exc:
                logging.error("💥 Critical: %s", exc)
                openclaw.send_message(f"💥 Critical error: {exc}")
                time.sleep(60)
    finally:
        openclaw.stop_command_listener()
