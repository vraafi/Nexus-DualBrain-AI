"""
main.py — Nexus DualBrain AI (OpenClaw Orchestrated)
======================================================
OpenClaw adalah cara UTAMA menjalankan agent ini.
File ini hanya FALLBACK jika OpenClaw tidak tersedia.

Cara menjalankan (REKOMENDASI — via OpenClaw):
  1. npm install -g openclaw@latest        # Install OpenClaw (butuh Node 24+)
  2. openclaw onboard                      # Setup interaktif: LLM key, Telegram, dll
  3. openclaw start                        # Jalankan gateway di port 18789
  4. Buka http://127.0.0.1:18789          # Dashboard web
  5. Chat via Telegram atau dashboard

OpenClaw akan otomatis:
  - Baca SOUL.md, AGENTS.md, HEARTBEAT.md dari ~/.openclaw/
  - Jalankan skills dari ~/.openclaw/skills/
  - Handle memori klien di ~/.openclaw/memory/clients/
  - Kontrol via Telegram (/status, /pause, /resume, /earnings)
  - Jadwal otomatis berdasarkan HEARTBEAT.md

Cara menjalankan TANPA OpenClaw (fallback):
  python main.py
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
from client_memory import ClientMemory
from openclaw_agent import OpenClawAgent

load_dotenv()

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
    """Tunggu sampai RAM < 85% dan CPU < 90% sebelum lanjut."""
    while True:
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent(interval=1)
        if ram > 85.0 or cpu > 90.0:
            logging.warning("Hardware kritis (RAM: %.1f%%, CPU: %.1f%%). Pause 60s...", ram, cpu)
            time.sleep(60)
        else:
            break


def build_shared_resources():
    api_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
                if os.environ.get(f"GEMINI_KEY_{i}")]
    if not api_keys:
        raise ValueError("CRITICAL: Tidak ada GEMINI_KEY_* di environment.")

    llm      = GeminiClient(api_keys)
    openclaw = OpenClawAgent(gemini_client=llm)
    branding = FreelanceBranding()
    finance  = FinancialTracker()
    memory   = ClientMemory()

    branding_strategies = {
        p: branding.get_branding_strategy(p)
        for p in ["upwork", "fiverr", "freelancer"]
    }
    return llm, openclaw, branding_strategies, finance, memory


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


def run_workflow(openclaw, finance, llm, branding_strategies, memory):
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
        logging.info("Agent dijeda. Menunggu /resume dari Telegram...")
        time.sleep(60)
        return SLEEP_DURATION_SHORT

    try:
        # ── Phase 1: Cek inbox & negosiasi ─────────────────────────────────────
        if current_step == "inbox_monitor_phase":
            _workflow_state["current_step"] = "inbox_monitor_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "inbox_monitor_phase", {})
            with BrowserAgent(headless=True) as browser:
                agent = FreelanceAgent(browser, llm)
                login_ok = agent.login_upwork()
            gc.collect()
            if login_ok:
                with BrowserAgent(headless=True) as browser:
                    agent = FreelanceAgent(browser, llm)
                    state, job_data = agent.check_messages_and_negotiate()
                gc.collect()
                if state in ("REVISION_REQUESTED", "CONTRACT_ACCEPTED"):
                    # Catat ke memori klien
                    if job_data:
                        memory.add_negotiation_note("upwork", "active_client", f"State: {state} — {job_data.get('title')}")
                    current_step = "code_generation_phase"
                else:
                    current_step = "freelance_phase"
            else:
                openclaw.send_message("⚠️ Upwork login gagal — perlu intervensi manual.")
                current_step = "freelance_phase"

        # ── Phase 2: Cari & apply job baru ─────────────────────────────────────
        if current_step == "freelance_phase":
            _workflow_state["current_step"] = "freelance_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "freelance_phase", {})
            with BrowserAgent(headless=True) as browser:
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

        # ── Phase 3: Generate kode ──────────────────────────────────────────────
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

            # Ambil konteks memori klien untuk ditambahkan ke prompt
            client_ctx = ""
            if job_data.get("platform") and job_data.get("client_username"):
                client_ctx = memory.get_context_for_llm(
                    job_data["platform"], job_data.get("client_username", "")
                )

            prompt = (
                f"Act as a senior Python developer. Complete this freelance job:\n"
                f"Platform: {job_data.get('platform', 'upwork')}\n"
                f"Title: {job_data.get('title')}\n"
                f"Description: {job_data.get('description')}\n"
            )
            if client_ctx:
                prompt += f"\nClient Context:\n{client_ctx}\n"
            prompt += (
                "\nRequirements:\n"
                "1. Complete, production-ready Python 3.10+ code\n"
                "2. Robust error handling (try/except on all I/O and network)\n"
                "3. Use logging module, not print()\n"
                "4. At least 3 unit tests using unittest\n"
                "5. Docstrings on all main functions\n"
                "6. Only standard library + requests, beautifulsoup4, or common libs\n"
                "7. Self-contained and runnable\n"
                "Output ONLY valid Python code, no markdown."
            )

            # Gunakan CODEGEN model (gemma-4-31b-it) — yang paling kuat
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

        # ── Phase 4: Sandbox test ───────────────────────────────────────────────
        if current_step == "sandbox_phase":
            _workflow_state["current_step"] = "sandbox_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})
            sandbox = SandboxTester(duration_minutes=15, llm_client=llm)
            passed = bool(sandbox.test_code(code_path))
            if not passed:
                openclaw.send_message("⚠️ Sandbox gagal 7x. Kembali ke pencarian job.")
                return SLEEP_DURATION_SHORT
            current_step = "delivery_phase"

        # ── Phase 5: Delivery ───────────────────────────────────────────────────
        if current_step == "delivery_phase":
            _workflow_state["current_step"] = "delivery_phase"
            wait_for_resources()
            if not job_data or not code_path:
                raise Exception("Data tidak lengkap untuk delivery.")
            platform = job_data.get("platform", "upwork").lower()
            save_state(task_id, "RUNNING", "delivery_phase",
                       {"job_data": job_data, "code_path": code_path})
            delivered = False
            with BrowserAgent(headless=True) as browser:
                if platform == "upwork":
                    agent = FreelanceAgent(browser, llm)
                    delivered = agent.deliver_work(job_data, code_path)
                elif platform == "fiverr":
                    agent = FiverrAgent(browser, llm)
                    delivered = agent.deliver_order(
                        job_data, code_path,
                        "Here is the completed, tested code. Let me know if you need any changes."
                    )
                elif platform == "freelancer":
                    agent = FreelancerAgent(browser, llm)
                    delivered = agent.deliver_work(job_data, code_path)
            gc.collect()
            if delivered:
                revenue = float(job_data.get("budget") or job_data.get("rate") or 50.0)
                finance.update_job_status(job_data.get("title"), "DELIVERED", revenue)

                # Update memori klien
                if job_data.get("client_username"):
                    memory.add_job(
                        platform,
                        job_data.get("client_username"),
                        job_data.get("title", ""),
                        revenue, "DELIVERED", revenue
                    )
                    memory.update_status(platform, job_data.get("client_username"), "DELIVERED")

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
    logging.info("")
    logging.info("REKOMENDASI: Gunakan OpenClaw untuk orkestrasi penuh!")
    logging.info("  1. npm install -g openclaw@latest")
    logging.info("  2. openclaw onboard")
    logging.info("  3. openclaw start")
    logging.info("  4. Buka http://127.0.0.1:18789")
    logging.info("=" * 60)

    llm, openclaw, branding_strategies, finance, memory = build_shared_resources()
    _workflow_state["start_time"] = time.time()

    openclaw.start_command_listener(
        status_callback=_get_status,
        finance_callback=finance.get_summary
    )
    openclaw.send_message(
        "🦞 Nexus DualBrain AI aktif (Python fallback mode).\n"
        "💡 Untuk fitur penuh: npm install -g openclaw@latest\n"
        "Kirim /help untuk daftar perintah."
    )

    try:
        while True:
            try:
                sleep_time = run_workflow(openclaw, finance, llm, branding_strategies, memory)
                logging.info("⏳ Cooldown %d detik...", sleep_time)
                time.sleep(sleep_time)
            except Exception as exc:
                logging.error("💥 Critical: %s", exc)
                openclaw.send_message(f"💥 Critical error: {exc}")
                time.sleep(60)
    finally:
        openclaw.stop_command_listener()
