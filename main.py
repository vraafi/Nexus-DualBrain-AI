"""
main.py — Nexus DualBrain AI
==============================
Satu perintah untuk menjalankan semua fitur:

  python3 main.py

Fitur yang aktif otomatis:
  ✓ Hermes Agent (skills, memory, Telegram gateway)
  ✓ Antigravity jika terinstall (autonomous local coding)
  ✓ GitHub CLI jika terinstall (issue/PR management)
  ✓ Sandbox tester (bwrap, 7x retry + auto-fix)
  ✓ Freelance orchestrator (Upwork, Fiverr, Freelancer)
  ✓ Client memory, Financial tracker

Kontrol via Telegram:
  /status, /pause, /resume, /earnings, /jobs, /help
"""

import gc
import time
import shutil
import subprocess
import logging
import uuid
import os
import psutil
from datetime import datetime, timezone, timedelta
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
from hermes_agent import HermesAgent
from skill_library import SkillLibrary
from job_scorer import JobScorer
from self_improver import SelfImprover
from payment_verifier import PaymentVerifier

load_dotenv()

RESIDENTIAL_PROXIES_STR = os.environ.get("RESIDENTIAL_PROXIES", "")
RESIDENTIAL_PROXIES = [p.strip() for p in RESIDENTIAL_PROXIES_STR.split(",") if p.strip()]

WIB = timezone(timedelta(hours=7))


def is_rest_hours() -> bool:
    """Cek apakah saat ini jam istirahat (11:00 - 17:00 WIB)."""
    hour = datetime.now(WIB).hour
    return 11 <= hour < 17


def wait_until_active(hermes=None):
    """
    Tunggu jika saat ini adalah waktu istirahat (11:00 - 17:00 WIB).
    Selama istirahat, Brave tetap terbuka tapi agent tidak melakukan aksi browser.
    """
    if not is_rest_hours():
        return

    now = datetime.now(WIB)
    wake = now.replace(hour=17, minute=0, second=0, microsecond=0)
    sleep_sec = (wake - now).total_seconds()
    logging.info(
        "😴 Jam istirahat (%02d:%02d WIB). Tidur %.1f jam hingga 17:00 WIB.",
        now.hour, now.minute, sleep_sec / 3600
    )
    if hermes:
        hermes.send_message(
            f"😴 Agent istirahat sampai 17:00 WIB ({sleep_sec/3600:.1f} jam lagi).\n"
            "Browser Brave tetap terbuka di halaman netral."
        )

    # Tidur, cek setiap 30 menit apakah sudah waktunya aktif
    while is_rest_hours():
        time.sleep(min(sleep_sec, 1800))
        sleep_sec = max(0, sleep_sec - 1800)

    logging.info("☀️ Waktu aktif dimulai! Lanjut kerja.")
    if hermes:
        hermes.send_message("☀️ Agent aktif kembali! Mulai mencari job.")


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

    llm           = GeminiClient(api_keys)
    hermes        = HermesAgent(gemini_client=llm)
    branding      = FreelanceBranding()
    finance       = FinancialTracker()
    memory        = ClientMemory()
    skill_lib     = SkillLibrary()
    job_scorer    = JobScorer(target_hourly_rate=float(os.environ.get("TARGET_HOURLY_RATE", 35)))
    self_improver = SelfImprover(llm_client=llm, skill_library=skill_lib, job_scorer=job_scorer)

    branding_strategies = {
        p: branding.get_branding_strategy(p)
        for p in ["upwork", "fiverr", "freelancer"]
    }
    return llm, hermes, branding_strategies, finance, memory, skill_lib, job_scorer, self_improver


_workflow_state = {
    "task_id": None,
    "current_step": "idle",
    "start_time": time.time(),
    "cycle_count": 0,
}


def _get_status():
    uptime = int(time.time() - _workflow_state.get("start_time", time.time()))
    h, rem = divmod(uptime, 3600)
    m, _ = divmod(rem, 60)
    return {
        "task_id": _workflow_state.get("task_id", "N/A"),
        "current_step": _workflow_state.get("current_step", "idle"),
        "uptime": f"{h}j {m}m",
        "cycle": _workflow_state.get("cycle_count", 0),
        "mode": "Nexus DualBrain AI aktif"
    }


def run_workflow(hermes, finance, llm, branding_strategies, memory,
                 skill_lib=None, job_scorer=None, self_improver=None):
    # ── REST HOURS CHECK ────────────────────────────────────────────────────
    if is_rest_hours():
        logging.info("🕐 Saat ini jam istirahat (%s WIB). Agent tidur.",
                     datetime.now(WIB).strftime("%H:%M"))
        wait_until_active(hermes)
        return SLEEP_DURATION_SHORT

    _workflow_state["cycle_count"] = _workflow_state.get("cycle_count", 0) + 1

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

    if hermes.is_paused:
        logging.info("Agent dijeda. Menunggu /resume dari Telegram...")
        time.sleep(60)
        return SLEEP_DURATION_SHORT

    try:
        # ── Phase 1: Cek inbox & negosiasi ─────────────────────────────────────
        if current_step == "inbox_monitor_phase":
            _workflow_state["current_step"] = "inbox_monitor_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "inbox_monitor_phase", {})
            current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
            with BrowserAgent(headless=False, proxy=current_proxy, endpoint_url="http://localhost:9222", llm_client=llm) as browser:
                agent = FreelanceAgent(browser, llm)
                login_ok = agent.login_upwork()
                # Navigasi ke halaman netral sebelum disconnect
                # agar Brave tetap di halaman aman, bukan Upwork
                browser.navigate_to_safe_page()
            gc.collect()
            if login_ok:
                current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
                with BrowserAgent(headless=False, proxy=current_proxy, endpoint_url="http://localhost:9222", llm_client=llm) as browser:
                    agent = FreelanceAgent(browser, llm)
                    state, job_data = agent.check_messages_and_negotiate()
                    # Navigasi ke halaman netral sebelum disconnect
                    browser.navigate_to_safe_page()
                gc.collect()
                if state in ("REVISION_REQUESTED", "CONTRACT_ACCEPTED"):
                    # Catat ke memori klien
                    if job_data:
                        memory.add_negotiation_note("upwork", "active_client", f"State: {state} — {job_data.get('title')}")
                    current_step = "code_generation_phase"
                else:
                    current_step = "freelance_phase"
            else:
                hermes.send_message("⚠️ Upwork login gagal — perlu intervensi manual.")
                current_step = "freelance_phase"

        # ── Phase 2: Cari & apply job baru ─────────────────────────────────────
        if current_step == "freelance_phase":
            _workflow_state["current_step"] = "freelance_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "freelance_phase", {})
            current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
            with BrowserAgent(headless=False, proxy=current_proxy, endpoint_url="http://localhost:9222", llm_client=llm) as browser:
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
            code_path = f"output/generated/{task_id[:8]}_{timestamp}_code.py"
            os.makedirs("output/generated", exist_ok=True)

            # Ambil konteks memori klien
            client_ctx = ""
            if job_data.get("platform") and job_data.get("client_username"):
                client_ctx = memory.get_context_for_llm(
                    job_data["platform"], job_data.get("client_username", "")
                )

            # ── Coba Jules CLI dulu (autonomous coding via GitHub) ───────────────────
            jules_path = shutil.which("jules")
            gh_path = shutil.which("gh")
            jules_ok = False

            if not jules_path:
                logging.warning("[Phase 3] ⚠️ Jules CLI tidak ditemukan di PATH! Fallback ke Gemini murni.")
            if not gh_path:
                logging.warning("[Phase 3] ⚠️ GitHub CLI (gh) tidak ditemukan di PATH! Fallback ke Gemini murni.")

            if jules_path and gh_path:
                try:
                    logging.info("[Phase 3] Jules CLI & GitHub CLI ditemukan di sistem. Membuat Repo Private baru...")

                    import re
                    # Buat nama repo yang aman dari nama klien dan judul tugas
                    client_name = job_data.get('client_username', 'client')
                    task_title = job_data.get('title', 'task')
                    safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', f"job-{client_name}-{task_title}-{task_id[:4]}").lower()
                    repo_name = safe_name[:100]  # limit panjang nama
                    full_repo_name = f"vraafi/{repo_name}"

                    # Create private repo
                    subprocess.run(
                        ["gh", "repo", "create", repo_name, "--private", "--add-readme"],
                        capture_output=True, text=True, check=False
                    )
                    logging.info("[Phase 3] Repo private dibuat: %s", full_repo_name)

                    # Buat GitHub Issue untuk Jules
                    issue_body = (
                        f"Platform: {job_data.get('platform', 'unknown')}\n"
                        f"Budget: {job_data.get('budget', 'N/A')}\n\n"
                        f"## Task Description\n{job_data.get('description', '')}\n\n"
                        f"## Requirements\n"
                        f"- Python 3.10+, production-ready\n"
                        f"- Error handling (try/except on I/O and network)\n"
                        f"- Logging module (not print())\n"
                        f"- Minimum 3 unit tests using unittest\n"
                        f"- Docstrings on all functions\n"
                        f"- Self-contained and runnable\n\n"
                        f"## Output Path\noutput/generated/{task_id[:8]}_{timestamp}_code.py"
                    )
                    issue_cmd = [
                        "gh", "issue", "create",
                        "--repo", full_repo_name,
                        "--title", f"FREELANCE JOB: {job_data.get('title', 'Coding Task')}",
                        "--body", issue_body,
                        "--label", "jules,freelance-job"
                    ]
                    issue_result = subprocess.run(
                        issue_cmd, capture_output=True, text=True, timeout=30
                    )
                    issue_url = issue_result.stdout.strip()
                    # Ambil nomor issue dari URL
                    issue_num = issue_url.rstrip("/").split("/")[-1]
                    logging.info("[Phase 3] GitHub Issue dibuat: #%s", issue_num)

                    # Trigger Jules untuk mengerjakan issue
                    jules_session = (
                        f"Implement the freelance coding job described in issue #{issue_num}. "
                        f"CRITICAL: You are encouraged to spawn parallel sub-agents to divide and conquer "
                        f"the task to finish it as fast as possible. "
                        f"Write complete Python 3.10+ code with unit tests. "
                        f"Save the output to output/generated/{task_id[:8]}_{timestamp}_code.py "
                        f"and create a PR when done."
                    )
                    jules_cmd = [
                        "jules", "remote", "new",
                        "--repo", full_repo_name,
                        "--parallel", "3",
                        "--session", jules_session
                    ]
                    logging.info("[Phase 3] Memulai Jules session... (Timeout dinaikkan ke 3 Jam karena sub-agents)")
                    hermes.send_message(
                        f"🤖 Jules sedang mengerjakan di repo private:\n`{full_repo_name}`\n"
                        f"Issue: #{issue_num}\nTunggu notifikasi PR (Maks 3 Jam)..."
                    )
                    jules_result = subprocess.run(
                        jules_cmd, capture_output=True, text=True, timeout=10800  # 3 Jam
                    )
                    if jules_result.returncode != 0:
                        logging.error("[Phase 3] Jules GAGAL: %s", jules_result.stderr)
                    else:
                        logging.info("[Phase 3] Jules session terkirim. Output: %s", jules_result.stdout[:500])

                    # Ambil kode dari PR Jules
                    pr_cmd = [
                        "gh", "pr", "list",
                        "--repo", full_repo_name,
                        "--label", "jules",
                        "--state", "open",
                        "--json", "number",
                        "--jq", ".[0].number"
                    ]
                    pr_result = subprocess.run(
                        pr_cmd, capture_output=True, text=True, timeout=30
                    )
                    pr_num = pr_result.stdout.strip()

                    if pr_num and pr_num.isdigit():
                        # Checkout kode dari PR
                        subprocess.run(
                            ["gh", "pr", "checkout", pr_num,
                             "--repo", full_repo_name],
                            timeout=60
                        )
                        if os.path.exists(code_path):
                            jules_ok = True
                            logging.info(
                                "[Phase 3] ✅ Jules berhasil! Kode diambil dari PR #%s", pr_num
                            )
                            hermes.send_message(
                                f"✅ Jules selesai coding! PR #{pr_num}\n"
                                f"Memulai sandbox testing..."
                            )
                except Exception as jules_err:
                    logging.warning("[Phase 3] Jules gagal: %s. Fallback ke internal LLM.", jules_err)

            # ── Evaluasi Hasil Jules CLI ───────────
            # ── Evaluasi Hasil Jules CLI & Fallback ke Antigravity/Aider ───────────
            if not jules_ok:
                logging.warning("[Phase 3] Jules gagal. Mencoba Fallback ke Antigravity/Aider...")

                antigravity_cli = shutil.which("antigravity")
                aider_cli = shutil.which("aider")
                fallback_success = False

                os.makedirs("output/generated", exist_ok=True)
                gemini_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
                               if os.environ.get(f"GEMINI_KEY_{i}")]
                if not gemini_keys:
                    gemini_keys = [os.environ.get("GEMINI_API_KEY", "DUMMY_KEY")]

                # ── Antigravity fallback ───────────────────────────────────────
                if antigravity_cli:
                    logging.info("[Phase 3] Mencoba Antigravity sebagai fallback...")
                    import random as _random
                    import re as _re
                    ag_keys = gemini_keys[:]
                    _random.shuffle(ag_keys)

                    task_desc = job_data.get("description", job_data.get("title", ""))
                    ag_prompt = (
                        f"Task: {job_data.get('title', 'Coding Task')}\n"
                        f"Description: {task_desc}\n\n"
                        "Write complete, production-ready Python 3.10+ code. "
                        f"Save it to the file '{os.path.basename(code_path)}'. "
                        "Include error handling, logging, and docstrings."
                    )

                    for ag_attempt, ag_key in enumerate(ag_keys):
                        logging.info("[Phase 3] Antigravity attempt %d...", ag_attempt + 1)
                        ag_env = os.environ.copy()
                        ag_env["GEMINI_API_KEY"] = ag_key
                        ag_cmd = [
                            antigravity_cli,
                            "--model", "gemini/gemini-3-flash",
                            "--message", ag_prompt,
                            "--yes-always",
                            "--auto-commits",
                            os.path.basename(code_path)
                        ]
                        ag_res = subprocess.run(
                            ag_cmd, cwd=os.path.dirname(os.path.abspath(code_path)) or ".",
                            env=ag_env, capture_output=True, text=True, timeout=300
                        )
                        if ag_res.returncode == 0 and os.path.exists(code_path):
                            fallback_success = True
                            logging.info("[Phase 3] ✅ Antigravity fallback berhasil!")
                            break
                        else:
                            logging.warning("[Phase 3] Antigravity attempt %d gagal.", ag_attempt + 1)

                # ── Aider fallback ─────────────────────────────────────────────
                if not fallback_success and aider_cli:
                    logging.info("[Phase 3] Antigravity gagal/tidak ada. Mencoba Aider sebagai fallback...")
                    task_desc = job_data.get("description", job_data.get("title", ""))
                    aider_cmd = [
                        aider_cli,
                        "--model", "gemini/gemma-4-31b-it",
                        "--message", (
                            f"Implement this task and save to '{os.path.basename(code_path)}':\n\n"
                            f"{task_desc}\n\n"
                            "Write complete Python 3.10+ code with error handling, logging, and docstrings."
                        ),
                        "--yes",
                        "--no-auto-commits",
                        os.path.basename(code_path)
                    ]
                    aider_env = os.environ.copy()
                    aider_env["GEMINI_API_KEY"] = gemini_keys[0]
                    aider_res = subprocess.run(
                        aider_cmd,
                        cwd=os.path.dirname(os.path.abspath(code_path)) or ".",
                        env=aider_env, capture_output=True, text=True, timeout=300
                    )
                    if os.path.exists(code_path):
                        fallback_success = True
                        logging.info("[Phase 3] ✅ Aider berhasil menyelesaikan tugas!")
                    else:
                        logging.error("[Phase 3] Aider gagal membuat file. stderr: %s",
                                      aider_res.stderr[:300])

                # ── LLM langsung sebagai last resort ──────────────────────────
                if not fallback_success:
                    logging.warning("[Phase 3] Antigravity & Aider gagal. Generate via LLM langsung...")
                    task_desc = job_data.get("description", job_data.get("title", ""))
                    llm_code = llm.generate_content(
                        f"Write complete, working Python 3.10+ code for:\n\n{task_desc}\n\n"
                        "Return ONLY raw Python code, no markdown fences.",
                        use_codegen_model=True
                    )
                    if llm_code:
                        if "```python" in llm_code:
                            llm_code = llm_code.split("```python")[1].split("```")[0]
                        elif "```" in llm_code:
                            llm_code = llm_code.split("```")[1]
                        import textwrap as _tw
                        llm_code = _tw.dedent(llm_code).strip()
                        with open(code_path, "w") as f:
                            f.write(llm_code)
                        fallback_success = True
                        logging.info("[Phase 3] ✅ LLM langsung berhasil generate kode: %s", code_path)

                if not fallback_success:
                    logging.error("[Phase 3] Semua coding agent (Jules, Antigravity, Aider, LLM) gagal.")
                    raise Exception("Gagal generate kode dengan semua agent yang tersedia.")
                
            current_step = "sandbox_phase"

        # ── Phase 4: Sandbox test ───────────────────────────────────────────────
        if current_step == "sandbox_phase":
            _workflow_state["current_step"] = "sandbox_phase"
            wait_for_resources()
            save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})
            sandbox = SandboxTester(duration_minutes=15, llm_client=llm)
            sandbox_result = sandbox.test_code(code_path)

            if not sandbox_result:
                # Sandbox failed — check if an apology file was written by the sandbox
                apology_file = "apology_message.txt"
                if os.path.exists(apology_file):
                    try:
                        with open(apology_file, "r") as f:
                            apology_text = f.read().strip()
                        if apology_text:
                            hermes.send_message(
                                f"⚠️ Sandbox gagal 7x. Apology untuk klien:\n\n{apology_text}"
                            )
                        # Clean up the apology file after sending
                        os.remove(apology_file)
                    except Exception as read_err:
                        logging.error("Gagal baca/kirim apology file: %s", read_err)
                else:
                    hermes.send_message("⚠️ Sandbox gagal. Kembali ke pencarian job.")

                save_state(task_id, "FAILED", "sandbox_failed", {"code": code_path})
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
            current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
            with BrowserAgent(headless=False, proxy=current_proxy, endpoint_url="http://localhost:9222") as browser:
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
                _workflow_state["total_deliveries"] = _workflow_state.get("total_deliveries", 0) + 1

                # Update memori klien
                if job_data.get("client_username"):
                    memory.add_job(
                        platform,
                        job_data.get("client_username"),
                        job_data.get("title", ""),
                        revenue, "DELIVERED", revenue
                    )
                    memory.update_status(platform, job_data.get("client_username"), "DELIVERED")

                # ── Phase 6: SKILL LIBRARY UPDATE ──────────────────────────
                if skill_lib and code_path and os.path.exists(code_path):
                    try:
                        with open(code_path, "r", encoding="utf-8") as f:
                            delivered_code = f.read()
                        skill_lib.save_success(
                            platform=platform,
                            job_title=job_data.get("title", ""),
                            job_description=job_data.get("description", ""),
                            code=delivered_code,
                            budget=revenue,
                        )
                        logging.info("[Phase 6] SkillLibrary diupdate dengan deliverable baru.")
                    except Exception as sk_err:
                        logging.error("[Phase 6] Gagal update SkillLibrary: %s", sk_err)

                # Record success metric
                if self_improver:
                    self_improver.record_metric("delivery_success", 1.0, job_data.get("title", ""))
                    self_improver.record_metric("revenue", revenue, platform)

                # Update job outcome di scorer
                if job_scorer and job_data.get("url"):
                    job_scorer.update_outcome(job_data["url"], "hired")

                stats_text = ""
                if skill_lib:
                    sk_stats = skill_lib.get_stats()
                    stats_text = f"\n📚 Skill templates: {sk_stats.get('total_skills', 0)}"

                hermes.send_message(
                    f"✅ DELIVERED!\nJob: {job_data.get('title')}\n"
                    f"Platform: {platform.upper()}\nRevenue: ${revenue:.2f}"
                    f"{stats_text}"
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

def run_coding_benchmarks(llm, hermes):
    """
    Jalankan 3 task coding (Easy, Medium, Hard) saat startup pertama kali
    untuk mengukur kemampuan AI agent dan membangun experience (skill library).
    """
    benchmark_file = "benchmark_completed.txt"
    if os.path.exists(benchmark_file):
        return  # Sudah pernah run benchmark

    logging.info("🚀 Memulai proses Benchmark Coding perdana (Easy, Medium, Hard)...")
    hermes.send_message("🚀 Menjalankan Coding Benchmark perdana (Easy, Medium, Hard) untuk kalibrasi agent...")

    tasks = [
        {
            "level": "HELLO",
            "title": "Antigravity Communication Test",
            "prompt": (
                "Write a Python script that simply prints 'Halo, saya Antigravity asli!'. "
                "This is a communication test to verify you are responding."
            )
        },
        {
            "level": "EASY",
            "title": "Custom Automation and Web Scraping",
            "prompt": (
                "Create a complete Python script using BeautifulSoup or requests to fetch "
                "a public webpage (e.g., a dummy product page or Wikipedia), parse 3 specific "
                "data points, and save them to a CSV file. Include fake user-agent rotation "
                "and robust error handling."
            )
        },
        {
            "level": "MEDIUM",
            "title": "Cloud Architecture & Microservices Migration (IaC)",
            "prompt": (
                "Simulate breaking down a monolith into microservices. Write a Python script "
                "that acts as an Infrastructure-as-Code (IaC) generator. The script must take a JSON "
                "configuration of 5 microservices (with dependencies) and automatically generate valid "
                "Kubernetes (K8s) Deployment and Service YAML manifests, as well as a basic Dockerfile "
                "for each. Include a simulated RabbitMQ message queue component in the architecture output."
            )
        },
        {
            "level": "HARD",
            "title": "Global-Scale Distributed Systems & Chaos Engineering",
            "prompt": (
                "Simulate re-architecting a real-time messaging system (like WhatsApp) for high throughput. "
                "Write a highly concurrent asynchronous Python script (using asyncio) that simulates "
                "thousands of messages being routed through a cluster of 5 nodes. Implement a 'Chaos Engineering' "
                "function that randomly kills nodes during execution. The remaining nodes must implement a simplified "
                "Raft or Paxos-like consensus mechanism to elect a new leader and ensure no messages are lost. "
                "Log the throughput and latency metrics at the end."
            )
        }
    ]

    from sandbox_tester import SandboxTester
    sandbox = SandboxTester(duration_minutes=5, llm_client=llm)
    
    results = []
    
    import re
    import time
    import random
    import glob as _glob
    for task in tasks:
        logging.info("📝 Menjalankan Benchmark %s: %s", task['level'], task['title'])

        safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', task['title']).lower()[:25]
        ts = int(time.time())

        # ── Gemini API keys ──────────────────────────────────────────────────
        gemini_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11)
                       if os.environ.get(f"GEMINI_KEY_{i}")]
        if not gemini_keys:
            gemini_keys = [os.environ.get("GEMINI_API_KEY", "DUMMY_KEY")]
        random.shuffle(gemini_keys)

        # ── Prompt yang sama untuk kedua agent ──────────────────────────────
        task_prompt = (
            f"Task: {task['title']}\n"
            f"Description: {task['prompt']}\n\n"
            "CRITICAL INSTRUCTION FOR AI AGENT:\n"
            "You are an expert developer working on a Fiverr Gig.\n"
            "1. WRITE CODE: Write complete, working Python 3.10+ code.\n"
            "2. Include error handling, logging, and docstrings.\n"
            "3. The code must be runnable with 'python3 <file>'.\n"
            "4. Save the code to the specified file.\n"
        )

        # ── Helper: buat repo GitHub + clone/init dir lokal ─────────────────
        def _setup_repo(agent_label, _safe_title=safe_title, _ts=ts, _task=task):
            rname = (f"sim-{_task['level'].lower()}-{agent_label}-"
                     f"{_safe_title}-{_ts}")
            full = f"vraafi/{rname}"
            subprocess.run(
                ["gh", "repo", "create", rname, "--private", "--add-readme"],
                capture_output=True, text=True, check=False
            )
            logging.info("[Benchmark] Repo %s dibuat: %s", agent_label.upper(), full)
            cdir = f"temp_{rname}"
            subprocess.run(["gh", "repo", "clone", full, cdir],
                           capture_output=True, text=True)
            if not os.path.isdir(cdir):
                logging.warning("[Benchmark] Clone %s gagal. Buat dir manual...",
                                agent_label)
                os.makedirs(cdir, exist_ok=True)
                subprocess.run(["git", "init"], cwd=cdir, capture_output=True)
                subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"],
                               cwd=cdir, capture_output=True)
                subprocess.run(["git", "config", "user.email",
                                "nexus-agent@replit.com"],
                               cwd=cdir, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Nexus DualBrain AI"],
                               cwd=cdir, capture_output=True)
                subprocess.run(
                    ["git", "remote", "add", "origin",
                     f"https://github.com/{full}.git"],
                    cwd=cdir, capture_output=True
                )
            return full, cdir

        # ── Helper: commit + push file ke repo ──────────────────────────────
        def _push_to_repo(cdir, fname, level, agent_label, full_rname):
            dest = os.path.join(cdir, fname)
            shutil.copy(fname, dest)
            subprocess.run(["git", "-C", cdir, "config", "user.email",
                            "nexus-agent@replit.com"], capture_output=True)
            subprocess.run(["git", "-C", cdir, "config", "user.name",
                            "Nexus DualBrain AI"], capture_output=True)
            subprocess.run(["git", "-C", cdir, "add", fname], capture_output=True)
            subprocess.run(
                ["git", "-C", cdir, "commit", "-m",
                 f"feat: {agent_label} benchmark {level} — sandbox PASSED"],
                capture_output=True, text=True
            )
            pr = subprocess.run(
                ["git", "-C", cdir, "push", "--set-upstream", "origin",
                 "HEAD:main"],
                capture_output=True, text=True
            )
            if pr.returncode == 0:
                logging.info("[Auto-Publish] ✅ %s di-push ke: %s",
                             agent_label.upper(), full_rname)
                hermes.send_message(
                    f"✅ Benchmark {level} [{agent_label.upper()}] LULUS sandbox!\n"
                    f"Repo: `{full_rname}`"
                )
            else:
                logging.error("[Auto-Publish] ❌ Gagal push %s: %s",
                              agent_label.upper(), pr.stderr[:300])

        # ── Buat DUA repo terpisah (satu Antigravity, satu Aider) ───────────
        full_ag_repo, ag_dir = _setup_repo("antigravity")
        full_aider_repo, aider_dir = _setup_repo("aider")
        antigravity_cli = shutil.which("antigravity")
        aider_cli_bin = shutil.which("aider")

        # ════════════════════════════════════════════════════════════════════
        # ANTIGRAVITY — jalankan di repo sendiri, cari file output-nya
        # ════════════════════════════════════════════════════════════════════
        ag_file = f"benchmark_{task['level'].lower()}_antigravity.py"
        ag_env = {**os.environ, "GEMINI_API_KEY": gemini_keys[0]}
        ag_found = False

        if antigravity_cli:
            for attempt, key in enumerate(gemini_keys):
                logging.info("[Benchmark] Menjalankan Antigravity (Attempt %d)...",
                             attempt + 1)
                ag_env["GEMINI_API_KEY"] = key
                ag_cmd = [
                    antigravity_cli,
                    "--model", "gemini/gemini-3-flash",
                    "--message", task_prompt,
                    "--yes-always", "--auto-commits",
                    "--mcp",
                    "C:/Users/user/.antigravity/Nexus-DualBrain-AI/mcp.json",
                    ag_file
                ]
                ag_res = subprocess.run(
                    ag_cmd, cwd=ag_dir, env=ag_env,
                    capture_output=True, text=True, timeout=300
                )
                if ag_res.stderr:
                    logging.error("[Antigravity STDERR]\n%s", ag_res.stderr)
                # Jika Antigravity berjalan sebagai Chromium/Electron,
                # flag tidak dikenal -- tidak akan pernah generate file; langsung break
                if ag_res.stderr and "is not in the list of known options" in ag_res.stderr:
                    logging.warning("[Benchmark] Antigravity terdeteksi sebagai Electron/Chromium. Langsung fallback ke LLM tanpa retry.")
                    break
                # Cari file output dengan nama eksplisit dulu
                if os.path.exists(os.path.join(ag_dir, ag_file)):
                    shutil.copy(os.path.join(ag_dir, ag_file), ag_file)
                    ag_found = True
                    break
                # Scan .py files di ag_dir jika nama file beda
                py_files = [
                    f for f in _glob.glob(os.path.join(ag_dir, "*.py"))
                    if os.path.basename(f) not in ("setup.py", "conftest.py")
                    and not os.path.basename(f).startswith("test_")
                ]
                if py_files:
                    py_files.sort(key=os.path.getsize, reverse=True)
                    shutil.copy(py_files[0], ag_file)
                    logging.info("[Benchmark] Antigravity file ditemukan via scan: %s",
                                 py_files[0])
                    ag_found = True
                    break

        if not ag_found:
            logging.warning("[Benchmark] Antigravity tidak buat file. "
                            "Generate via LLM untuk repo Antigravity...")
            llm_code = llm.generate_content(
                f"Write complete, working Python 3.10+ code for:\n\n"
                f"{task['prompt']}\n\nReturn ONLY raw Python code.",
                use_codegen_model=True
            )
            if llm_code:
                if "```python" in llm_code:
                    llm_code = llm_code.split("```python")[1].split("```")[0]
                elif "```" in llm_code:
                    llm_code = llm_code.split("```")[1]
                import textwrap as _tw
                llm_code = _tw.dedent(llm_code).strip()
                with open(ag_file, "w") as f:
                    f.write(f"# Generated by LLM (Antigravity fallback)\n{llm_code}\n")
                ag_found = True

        # ════════════════════════════════════════════════════════════════════
        # AIDER — jalankan secara independen di repo sendiri
        # ════════════════════════════════════════════════════════════════════
        aider_file = f"benchmark_{task['level'].lower()}_aider.py"
        aider_env = {**os.environ, "GEMINI_API_KEY": gemini_keys[0]}
        aider_found = False

        if aider_cli_bin:
            logging.info("[Benchmark] Menjalankan Aider (independen)...")
            aider_cmd = [
                aider_cli_bin,
                "--model", "gemini/gemma-4-31b-it",
                "--message", (
                    f"{task_prompt}\n\n"
                    f"WAJIB: Simpan kode ke file '{aider_file}'. "
                    "Pastikan file dibuat dan bisa dijalankan."
                ),
                "--yes", "--no-auto-commits",
                aider_file
            ]
            aider_res = subprocess.run(
                aider_cmd, cwd=aider_dir, env=aider_env,
                capture_output=True, text=True, timeout=300
            )
            if os.path.exists(os.path.join(aider_dir, aider_file)):
                shutil.copy(os.path.join(aider_dir, aider_file), aider_file)
                aider_found = True
                logging.info("[Benchmark] ✅ Aider berhasil membuat: %s", aider_file)
            else:
                logging.warning("[Benchmark] Aider tidak buat file. "
                                "Generate via LLM untuk repo Aider...")

        if not aider_found:
            llm_code = llm.generate_content(
                f"Write complete, working Python 3.10+ code for:\n\n"
                f"{task['prompt']}\n\nReturn ONLY raw Python code.",
                use_codegen_model=True
            )
            if llm_code:
                if "```python" in llm_code:
                    llm_code = llm_code.split("```python")[1].split("```")[0]
                elif "```" in llm_code:
                    llm_code = llm_code.split("```")[1]
                import textwrap as _tw
                llm_code = _tw.dedent(llm_code).strip()
                with open(aider_file, "w") as f:
                    f.write(f"# Generated by LLM (Aider fallback)\n{llm_code}\n")
                aider_found = True

        # ════════════════════════════════════════════════════════════════════
        # SANDBOX TEST + PUSH — masing-masing agent independen
        # ════════════════════════════════════════════════════════════════════
        for agent_label, file_local, cdir, full_repo in [
            ("Antigravity", ag_file, ag_dir, full_ag_repo),
            ("Aider", aider_file, aider_dir, full_aider_repo),
        ]:
            if not os.path.exists(file_local):
                logging.error("[Benchmark] %s: file tidak ada — skip.", agent_label)
                results.append(
                    f"{task['level']} [{agent_label}] ({task['title']}): ❌ NO FILE"
                )
                continue

            logging.info("[Benchmark] Menguji kode %s di sandbox...", agent_label)
            passed = sandbox.test_code(file_local)
            status = "✅ PASSED" if passed else "❌ FAILED"
            results.append(
                f"{task['level']} [{agent_label}] ({task['title']}): {status}"
            )

            if passed:
                logging.info("[Benchmark] %s LULUS. Push ke GitHub...", agent_label)
                _push_to_repo(cdir, file_local, task['level'], agent_label, full_repo)
            else:
                logging.warning("[Benchmark] ❌ %s GAGAL sandbox. Tidak di-push.",
                                agent_label)
                hermes.send_message(
                    f"❌ Benchmark {task['level']} [{agent_label.upper()}] "
                    f"GAGAL sandbox. Kode tidak di-push."
                )

        
    # Kirim hasil ke user
    result_text = "\n".join(results)
    hermes.send_message(
        f"📊 Hasil Coding Benchmark:\n\n{result_text}\n\n"
        f"File kode telah disimpan di folder repository: benchmark_easy.py, "
        f"benchmark_medium.py, dan benchmark_hard.py.\nSilakan direview!"
    )
    
    with open(benchmark_file, "w") as f:
        f.write("Completed: " + time.strftime("%Y-%m-%d %H:%M:%S"))
    logging.info("✅ Benchmark selesai.")

if __name__ == "__main__":
    init_db()

    # ── DETEKSI TOOLS YANG TERSEDIA ──────────────────────────────────────────
    hermes_cli  = shutil.which("hermes")
    antigravity_cli   = shutil.which("antigravity")
    aider_cli   = shutil.which("aider")
    gh_cli      = shutil.which("gh")

    logging.info("=" * 60)
    logging.info("Nexus DualBrain AI — Autonomous Freelance Agent")
    logging.info("=" * 60)
    logging.info("✅ Hermes Agent (skills, memory, Telegram) : AKTIF")
    logging.info("%s Antigravity (autonomous local coding)   : %s",
                 "✅" if antigravity_cli else "⚠️ ", "AKTIF" if antigravity_cli else "tidak terinstall")
    logging.info("%s Aider (fallback coding agent)           : %s",
                 "✅" if aider_cli else "⚠️ ", "AKTIF" if aider_cli else "tidak terinstall")
    logging.info("%s GitHub CLI (issue/PR management)       : %s",
                 "✅" if gh_cli else "⚠️ ", "AKTIF" if gh_cli else "tidak terinstall")
    logging.info("%s Hermes CLI (optional, extra features)  : %s",
                 "✅" if hermes_cli else "ℹ️ ", "terinstall" if hermes_cli else "tidak terinstall")
    logging.info("=" * 60)

    llm, hermes, branding_strategies, finance, memory, skill_lib, job_scorer, self_improver = build_shared_resources()
    _workflow_state["start_time"] = time.time()

    hermes.start_command_listener(
        status_callback=_get_status,
        finance_callback=finance.get_summary
    )

    # ── KIRIM STATUS STARTUP KE TELEGRAM ────────────────────────────────
    antigravity_status = "✅ AKTIF — local coding" if antigravity_cli else "⚠️ tidak terinstall (fallback: LLM)"
    gh_status    = "✅ AKTIF" if gh_cli else "⚠️ tidak terinstall"
    hermes.send_message(
        "🧠 *Nexus DualBrain AI — Online*\n\n"
        "✅ Hermes Agent: aktif\n"
        "✅ Skills: Upwork, Fiverr, Freelancer, Codegen, Sandbox, Deliver\n"
        "✅ Client memory: aktif\n"
        "✅ Financial tracker: aktif\n"
        "✅ Telegram: aktif\n"
        f"Antigravity: {antigravity_status}\n"
        f"GitHub CLI: {gh_status}\n\n"
        "Ketik /help untuk daftar perintah.",
        markdown=True
    )

    # ── OPSIONAL: Spawn Hermes CLI di background jika terinstall ───────────────
    if hermes_cli:
        try:
            logging.info("[Hermes CLI] Menjalankan hermes --goal di background...")
            hermes_goal = (
                "Kamu adalah Nexus DualBrain AI, autonomous freelance agent. "
                "Gunakan skills yang tersedia untuk: cari job Python di Upwork dan Fiverr, "
                "generate kode dengan Jules CLI, test di sandbox, dan deliver ke klien. "
                "Jadwal aktif: 17:00-11:00 WIB."
            )
            subprocess.Popen(
                [hermes_cli, "--goal", hermes_goal],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logging.info("[Hermes CLI] ✅ Hermes CLI berjalan di background.")
        except Exception as e:
            logging.warning("[Hermes CLI] Gagal spawn Hermes CLI: %s", e)

    # ── BENCHMARK KALIBRASI (sekali saat startup) ───────────────────────────
    run_coding_benchmarks(llm, hermes)

    # ── PAYMENT VERIFICATION SCHEDULE ─────────────────────────────────────
    # Verifikasi pembayaran dijalankan sekali per 24 jam.
    # Ini yang update status "DELIVERED" -> "PAID" di FinancialTracker.
    # Reference: https://support.upwork.com/hc/en-us/articles/211062608
    _last_payment_check = 0
    PAYMENT_CHECK_INTERVAL = 86400  # 24 jam

    # ── MAIN LOOP ────────────────────────────────────────────────────
    try:
        while True:
            try:
                sleep_time = run_workflow(
                    hermes, finance, llm, branding_strategies, memory,
                    skill_lib=skill_lib,
                    job_scorer=job_scorer,
                    self_improver=self_improver
                )
                logging.info("Cooldown %d detik...", sleep_time)

                # Jalankan payment verification setiap 24 jam
                if time.time() - _last_payment_check > PAYMENT_CHECK_INTERVAL:
                    try:
                        logging.info("[PaymentVerifier] Memulai verifikasi pembayaran harian...")
                        current_proxy = get_next_proxy(RESIDENTIAL_PROXIES)
                        with BrowserAgent(headless=False, proxy=current_proxy,
                                          endpoint_url="http://localhost:9222",
                                          llm_client=llm) as pay_browser:
                            verifier = PaymentVerifier(pay_browser, llm, finance)
                            results = verifier.run_full_verification()

                        if results["total_new_payments"] > 0:
                            summary = finance.get_summary()
                            hermes.send_message(
                                f"💰 Verifikasi Pembayaran Selesai!\n"
                                f"Pembayaran baru: {results['total_new_payments']}\n"
                                f"Total revenue: ${summary.get('total_revenue', 0):.2f}\n"
                                f"Pending: ${summary.get('pending_revenue', 0):.2f}"
                            )
                        _last_payment_check = time.time()
                    except Exception as pay_err:
                        logging.error("[PaymentVerifier] Error: %s", pay_err)

                time.sleep(sleep_time)
            except Exception as exc:
                logging.error("Critical workflow error: %s", exc)
                hermes.send_message(f"Critical error: {exc}")
                time.sleep(60)
    finally:
        hermes.stop_command_listener()
        logging.info("Nexus DualBrain AI dihentikan.")
