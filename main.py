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
                            llm_code = llm_code.split("```python")[1].split("```")[0].strip()
                        elif "```" in llm_code:
                            llm_code = llm_code.split("```")[1].strip()
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
    for task in tasks:
        logging.info("📝 Menjalankan Benchmark %s: %s", task['level'], task['title'])
        
        safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', task['title']).lower()[:30]
        repo_name = f"sim-{task['level'].lower()}-{safe_title}-{int(time.time())}"
        full_repo_name = f"vraafi/{repo_name}"
        
        # 1. Create Private Repo & Clone locally
        subprocess.run(
            ["gh", "repo", "create", repo_name, "--private", "--add-readme"],
            capture_output=True, text=True, check=False
        )
        logging.info("[Benchmark] Repo private dibuat: %s", full_repo_name)

        # Clone repo tersebut ke folder temp
        clone_dir = f"temp_{repo_name}"
        subprocess.run(["gh", "repo", "clone", full_repo_name, clone_dir], capture_output=True, text=True)

        # 2. Persiapan Prompt Antigravity (Dengan Proteksi Requirement & 10x Retry)
        antigravity_prompt = (
            f"Task: {task['title']}\n"
            f"Description: {task['prompt']}\n\n"
            "CRITICAL INSTRUCTION FOR AI AGENT:\n"
            "You are an expert developer working on a Fiverr Gig.\n"
            "Before writing any code, CRITICALLY ANALYZE the client's requirements above.\n"
            "If the requirements are ambiguous, use the MCP tool 'ask_client_question' to ask for clarification.\n"
            "1. WRITE CODE: Write the Python script to the requested file.\n"
            "2. TERMINAL TEST: You MUST use the MCP tool 'request_hermes_to_test_code' to ask Hermes to run your code in the terminal.\n"
            "3. FIX/DEBATE: If Hermes returns a terminal ERROR log, read the log carefully. Fix your code and call the test tool again. If the error is weird, you can debate or apologize and rewrite.\n"
            "4. UPGRADE: If Hermes returns a SUCCESS log, review it. If it can be upgraded for better quality, edit and test again.\n"
            "5. FINAL SUBMISSION: Once perfectly tested and working, use the MCP tool 'submit_code_for_testing' to finalize delivery.\n"
        )

        logging.info("[Benchmark] Memanggil Antigravity...")
        
        # Ambil semua API Key dari environment
        gemini_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11) if os.environ.get(f"GEMINI_KEY_{i}")]
        if not gemini_keys:
            gemini_keys = ["DUMMY_KEY"] # Fallback if empty
            
        import random
        random.shuffle(gemini_keys) # Acak urutan key untuk rotasi
        
        # 1. Jalankan Antigravity Terlebih Dahulu
        antigravity_success = False
        for attempt, key in enumerate(gemini_keys):
            logging.info(f"[Benchmark] Menjalankan Antigravity (Attempt {attempt+1})...")
            antigravity_env = os.environ.copy()
            antigravity_env["GEMINI_API_KEY"] = key
            
            file_name_antigravity = f"benchmark_{task['level'].lower()}_antigravity.py"
            antigravity_cmd = [
                "antigravity",
                "--model", "gemini/gemini-3-flash",
                "--message", antigravity_prompt,
                "--yes-always",
                "--auto-commits",
                "--mcp", "C:/Users/user/.antigravity/Nexus-DualBrain-AI/mcp.json",
                file_name_antigravity
            ]
            antigravity_process = subprocess.run(antigravity_cmd, cwd=clone_dir, env=antigravity_env, capture_output=True, text=True)
            
            if antigravity_process.returncode == 0:
                antigravity_success = True
                hermes.send_message(f"✅ Antigravity sukses mengerjakan tugas: {task['level']}", markdown=True)
                break
            else:
                logging.warning(f"⚠️ Antigravity gagal pada attempt {attempt+1}. Mencoba key lain...")

        # 2. Jalankan Aider Setelah Antigravity Selesai (Sekuensial)
        aider_success = False
        aider_cli = shutil.which("aider")
        if aider_cli:
            logging.info(f"[Benchmark] Menjalankan Aider (Sekuensial)...")
            file_name_aider = f"benchmark_{task['level'].lower()}_aider.py"
            aider_cmd = [aider_cli, "--model", "gemini/gemma-4-31b-it", "--message", antigravity_prompt, "--yes", "--no-auto-commits"]
            # Berikan file name spesifik agar tidak konflik dengan file antigravity
            aider_res = subprocess.run(aider_cmd, cwd=clone_dir, env=antigravity_env, capture_output=True, text=True)
            if aider_res.returncode == 0:
                aider_success = True
                hermes.send_message(f"✅ Aider sukses mengerjakan tugas: {task['level']}", markdown=True)
            else:
                hermes.send_message(f"❌ Aider gagal pada tugas: {task['level']}", markdown=True)

        logging.info("[Antigravity STDOUT]\n%s", antigravity_process.stdout if antigravity_process else "")
        if antigravity_process and antigravity_process.stderr:
            logging.error("[Antigravity STDERR]\n%s", antigravity_process.stderr)
        
        # Evaluasi hasil Antigravity
        output_for_eval = (antigravity_process.stdout or "") + "\n" + (antigravity_process.stderr or "")
        # Gunakan regex sederhana: cari kata kunci NEED_INFO yang bukan bagian dari rincian instruksi (THINKING)
        # Biasanya Antigravity akan membalas di bagian ► ANSWER
        if "► ANSWER\n\nNEED_INFO:" in output_for_eval or "► ANSWER\nNEED_INFO:" in output_for_eval:
            try:
                # Potong mulai dari NEED_INFO di dalam blok answer
                answer_block = output_for_eval.split("► ANSWER")[1]
                questions = answer_block.split("NEED_INFO:")[1].split('\n\n\n')[0].strip()
            except:
                questions = "Tolong berikan detail lebih spesifik mengenai arsitektur atau input yang Anda harapkan."
                
            logging.warning("🚨 [Antigravity Pause] Kebutuhan klien tidak jelas. Antigravity menunda task dan meminta info: %s", questions)
            
            # Hubungkan ke Telegram Hermes untuk diteruskan ke klien Fiverr/Upwork
            try:
                # Karena ini ada di scope lokal main.py, kita kirim log ke console, 
                # di real life ini akan diteruskan oleh freelance_orchestrator
                logging.info(f"Mengirim pesan ke klien Fiverr: 'Halo! Terkait gig ini, tim developer kami membutuhkan informasi tambahan: {questions}'")
            except:
                pass
                
            # Jangan lakukan push, skip task ini sampai klien menjawab
            continue

        logging.info("[Benchmark] Antigravity selesai memproses file! Mem-push ke GitHub...")
        push_res = subprocess.run(["git", "-C", clone_dir, "push", "origin", "main"], capture_output=True, text=True)
        if push_res.returncode == 0:
            logging.info("[Auto-Publish] ✅ SUKSES! Antigravity berhasil mem-push kode langsung ke main branch.")
        else:
            logging.error("[Auto-Publish] Gagal git push: %s", push_res.stderr)

        # 4. Pindahkan kode murni buatan Antigravity ke luar untuk dites Sandbox
        file_name = f"benchmark_{task['level'].lower()}.py"
        target_file = os.path.join(clone_dir, file_name)

        # Cari semua kandidat file .py yang mungkin dibuat Antigravity/Aider di clone_dir
        file_found = False
        candidates = [
            target_file,
            os.path.join(clone_dir, file_name_antigravity),
            os.path.join(clone_dir, f"benchmark_{task['level'].lower()}_aider.py"),
            os.path.join(clone_dir, "solution.py"),
            os.path.join(clone_dir, "main.py"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                shutil.copy(candidate, file_name)
                logging.info("[Benchmark] Berhasil mengekstrak kode dari: %s", candidate)
                file_found = True
                break

        # Jika tidak ada file yang dibuat oleh Antigravity/Aider, scan semua .py di clone_dir
        if not file_found:
            import glob as _glob
            py_files = [
                f for f in _glob.glob(os.path.join(clone_dir, "*.py"))
                if not os.path.basename(f).startswith("test_")
                and os.path.basename(f) not in ("setup.py", "conftest.py")
            ]
            if py_files:
                # Ambil file terbesar (kemungkinan besar itulah kode utama)
                py_files.sort(key=os.path.getsize, reverse=True)
                shutil.copy(py_files[0], file_name)
                logging.info("[Benchmark] File Antigravity ditemukan via scan: %s", py_files[0])
                file_found = True

        # Fallback ke Aider dengan output file eksplisit jika semua gagal
        if not file_found and aider_cli:
            logging.warning("[Benchmark] Antigravity tidak buat file. Fallback Aider dengan output eksplisit...")
            aider_fallback_cmd = [
                aider_cli,
                "--model", "gemini/gemma-4-31b-it",
                "--message", (
                    f"{antigravity_prompt}\n\n"
                    f"WAJIB: Simpan kode ke file bernama '{file_name}'. "
                    "Pastikan file dibuat dan bisa dijalankan."
                ),
                "--yes",
                "--no-auto-commits",
                file_name
            ]
            aider_fb_res = subprocess.run(
                aider_fallback_cmd, cwd=clone_dir,
                env=antigravity_env, capture_output=True, text=True, timeout=300
            )
            if os.path.exists(os.path.join(clone_dir, file_name)):
                shutil.copy(os.path.join(clone_dir, file_name), file_name)
                logging.info("[Benchmark] ✅ Aider fallback berhasil membuat file: %s", file_name)
                file_found = True
            else:
                logging.error("[Benchmark] Aider fallback juga gagal membuat file. Error: %s",
                              aider_fb_res.stderr[:200])

        # Last resort: generate langsung via Gemini LLM
        if not file_found:
            logging.warning("[Benchmark] Semua agent gagal membuat file. Generate via LLM langsung...")
            llm_code = llm.generate_content(
                f"Write complete, working Python code for this task:\n\n{task['prompt']}\n\n"
                "Return ONLY the raw Python code, no markdown fences.",
                use_codegen_model=True
            )
            if llm_code:
                # Strip markdown jika ada
                if "```python" in llm_code:
                    llm_code = llm_code.split("```python")[1].split("```")[0].strip()
                elif "```" in llm_code:
                    llm_code = llm_code.split("```")[1].strip()
                with open(file_name, "w") as f:
                    f.write(llm_code)
                logging.info("[Benchmark] ✅ LLM langsung berhasil generate kode untuk: %s", file_name)
                file_found = True
            else:
                with open(file_name, "w") as f:
                    f.write(f"# ERROR: Semua agent gagal membuat kode untuk task: {task['title']}\n")
                logging.error("[Benchmark] Semua fallback gagal untuk task: %s", task['level'])
                
        # 5. Test di Sandbox (Gemma 4 menguji Jules)
        passed = sandbox.test_code(file_name)
        status = "✅ PASSED" if passed else "❌ FAILED"
        results.append(f"{task['level']} ({task['title']}): {status}")
        
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
                logging.info("⏳ Cooldown %d detik...", sleep_time)
                time.sleep(sleep_time)
            except Exception as exc:
                logging.error("💥 Critical workflow error: %s", exc)
                hermes.send_message(f"💥 Critical error: {exc}")
                time.sleep(60)
    finally:
        hermes.stop_command_listener()
        logging.info("Nexus DualBrain AI dihentikan.")
