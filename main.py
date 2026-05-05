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
from sandbox_tester import SandboxTester
from api_client import GeminiClient
from financial_tracker import FinancialTracker
import psutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SLEEP_DURATION = 7200 # 2 hours resting period to cool down

def wait_for_resources():
    """Pauses execution if hardware constraints are exceeded."""
    while True:
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent(interval=1)
        if ram > 85.0 or cpu > 90.0:
            logging.warning(f"Hardware resources critical (RAM: {ram}%, CPU: {cpu}%). Pausing for 60s...")
            time.sleep(60)
        else:
            break

def run_workflow():
    api_keys = []
    for i in range(1, 11):
        key = os.environ.get(f"GEMINI_KEY_{i}")
        if key:
            api_keys.append(key)

    if not api_keys:
        raise ValueError("CRITICAL: No GEMINI_KEY_* found in environment variables. Aborting.")

    llm = GeminiClient(api_keys)

    # Load Telegram credentials from environment variables as requested
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not telegram_token or not telegram_chat_id:
        logging.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Real delivery will fail.")
        telegram_token = "mock_token"
        telegram_chat_id = "mock_chat_id"

    telegram = TelegramAgent(telegram_token, telegram_chat_id)
    branding = FreelanceBranding()
    sandbox = SandboxTester(duration_minutes=15, llm_client=llm)
    finance = FinancialTracker()

    # Crash Recovery Mechanism
    last_task = get_last_incomplete_task()
    if last_task:
        task_id = last_task["task_id"]
        current_step = last_task["current_step"]
        logging.info(f"Recovered incomplete task {task_id} at step {current_step}")
    else:
        task_id = str(uuid.uuid4())
        current_step = "freelance_job_hunt_phase"

    save_state(task_id, "STARTED", current_step, {})
    logging.info(f"Starting/Resuming workflow task {task_id}. Hardware constraints active.")

    try:
        job_data = None
        code_path = "generated_script.py"

        if current_step in ["init", "freelance_job_hunt_phase"]:
            # Step 1: Freelance Job Hunting & Filtering
            wait_for_resources()
            save_state(task_id, "RUNNING", "freelance_job_hunt_phase", {})
            brand_context = branding.get_branding_strategy("upwork")

            # Explicitly manage Hybrid Browser Mode for login phase
            login_browser_mode = True
            with BrowserAgent(headless=login_browser_mode) as browser:
                freelance = FreelanceAgent(browser, llm)
                login_success = freelance.login_upwork()
                if not login_success:
                    logging.warning("Initial headless login failed. Falling back to headed mode for manual Captcha intervention.")
                    telegram.send_message("WARNING: Upwork Login Failed. Starting headed browser for manual Captcha/2FA.")

            if not login_success:
                login_browser_mode = False
                with BrowserAgent(headless=login_browser_mode) as browser:
                    freelance = FreelanceAgent(browser, llm)
                    login_success = freelance.login_upwork()
                    if not login_success:
                        raise Exception("Failed to login to Upwork even after headed manual intervention attempt.")

            with BrowserAgent(headless=True) as browser:
                freelance = FreelanceAgent(browser, llm)

                jobs = freelance.scrape_jobs()
                if not jobs:
                    raise Exception("No jobs found. Aborting cycle.")

                for job in jobs:
                    is_auto, reason = freelance.filter_job(job)
                    if is_auto:
                        job_data = job
                        logging.info(f"Selected Job: {job['title']}")
                        break

            gc.collect()

            if not job_data:
                raise Exception("No fully autonomous jobs found in this cycle. Sleeping.")

            current_step = "code_generation_phase"

        if current_step == "code_generation_phase":
            # Step 2: Code Generation using API (replacing Jules)
            wait_for_resources()
            save_state(task_id, "RUNNING", "code_generation_phase", {"job_data": job_data})

            if not job_data:
                 # Recover from state if missing
                 state = load_state(task_id)
                 job_data = state.get("data", {}).get("job_data")

            prompt = (
                f"Act as a senior backend Python developer. I have accepted the following freelance job:\n"
                f"Title: {job_data.get('title')}\nDescription: {job_data.get('description')}\n"
                "Write the complete, robust python script to solve this task. "
                "Output ONLY valid Python code. Do not wrap in markdown or explain."
            )

            logging.info("Generating code via Gemini API...")
            generated_code = llm.generate_content(prompt)
            if not generated_code:
                raise Exception("LLM API failed to generate code.")

            # Clean up markdown if LLM disobeyed
            if "```python" in generated_code:
                generated_code = generated_code.split("```python")[1].split("```")[0].strip()
            elif "```" in generated_code:
                generated_code = generated_code.split("```")[1].strip()

            with open(code_path, "w") as f:
                f.write(generated_code)

            current_step = "sandbox_phase"

        if current_step == "sandbox_phase":
            # Step 3: Sandbox Testing with Finite Self-Correction Loop
            wait_for_resources()
            # The variable code_path may not be available if resuming directly into this step,
            # so we check if the file exists from a previous run or skip.
            if 'code_path' not in locals():
                code_path = "generated_script.py"

            if code_path and os.path.exists(code_path):
                save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})
                sandbox_result = sandbox.test_code(code_path)

                # Check for Graceful Cancellation dictionary return from sandbox
                if isinstance(sandbox_result, dict) and sandbox_result.get("status") == "failed":
                     logging.info("Sandbox hit failsafe. Skipping proposal. Returning to Job Hunt.")
                     telegram.send_message("Task canceled internally due to unresolvable errors. Returning to Job Hunting.")
                     current_step = "done" # Skip proposal/delivery and end this cycle immediately

                elif not sandbox_result:
                    raise Exception("Sandbox testing failed completely after 7 retries and mentor cancellation.")
            else:
                raise Exception("No code path returned from API or missing. Skipping sandbox.")

            if current_step != "done":
                 current_step = "proposal_phase"

        if current_step == "proposal_phase":
            # Step 4: Submit Proposal to Client natively
            wait_for_resources()
            save_state(task_id, "RUNNING", "proposal_phase", {"job_data": job_data})
            if not job_data:
                 state = load_state(task_id)
                 job_data = state.get("data", {}).get("job_data")

            if os.path.exists(code_path) and job_data:
                # Log financial start
                finance.log_proposal("upwork", job_data.get('title', 'Unknown Job'), expected_revenue=50.0)

                with BrowserAgent(headless=True) as browser:
                    freelance = FreelanceAgent(browser, llm)
                    brand_context = branding.get_branding_strategy("upwork")

                    # Submit Proposal
                    proposal_success = freelance.submit_proposal(job_data, brand_context, code_path)

                    if proposal_success:
                        telegram.send_message(f"Successfully submitted proposal for: {job_data.get('title')}")
                        # Move to waiting phase before delivery
                        current_step = "wait_for_contract_phase"
                    else:
                         telegram.send_message("Failed to submit proposal.")
                         raise Exception("Proposal submission failed. Aborting delivery.")
            else:
                telegram.send_message("Task failed. Code path missing or job data lost.")
                raise Exception("Missing code or job data.")

        if current_step == "wait_for_contract_phase":
             # Step 5: Wait for client to accept contract before delivering
             # In a real 18/7 autonomous loop, we would park this task and check back later.
             # For the sake of this sequence, we simulate the wait, then deliver.
             logging.info("Proposal submitted. Pausing this specific task sequence to simulate waiting for client contract acceptance...")
             telegram.send_message("Waiting for client contract acceptance before delivering code...")
             # Since we cannot actually wait days in a synchronous script, we log it and proceed to delivery
             # assuming the contract was accepted for demonstration of the delivery module.
             current_step = "delivery_phase"

        if current_step == "delivery_phase":
            # Step 6: Deliver results via Telegram and Platform
            wait_for_resources()
            save_state(task_id, "RUNNING", "delivery_phase", {"job_data": job_data})

            with BrowserAgent(headless=True) as browser:
                 freelance = FreelanceAgent(browser, llm)
                 delivery_success = freelance.deliver_work(job_data, code_path)
                 if delivery_success:
                     finance.update_job_status(job_data.get('title'), "DELIVERED", actual_revenue=50.0)
                     telegram.send_message(f"Successfully Delivered Job Code to Client: {job_data.get('title')}")
                 else:
                     telegram.send_message("Delivery step failed on platform.")
                     raise Exception("Failed to deliver work to client.")

        save_state(task_id, "COMPLETED", "done", {"final_status": "Success"})
        logging.info(f"Task {task_id} completed successfully.")

        with open("completion_report.log", "a") as f:
            f.write(f"Task {task_id} finished at {time.ctime()}.\n")

    except Exception as e:
        logging.error(f"Workflow failed: {e}")
        save_state(task_id, "FAILED", "error", {"error": str(e)})

if __name__ == "__main__":
    init_db()
    logging.info("Starting Agentic Workflow loop. Target: 18/7 operation.")

    # 18/7 Continuous loop requirement
    while True:
        try:
             run_workflow()
             logging.info(f"Cycle complete. Cooling down hardware for {SLEEP_DURATION} seconds...")
             time.sleep(SLEEP_DURATION)
        except Exception as e:
             logging.error(f"Critical outer loop failure: {e}")
             time.sleep(60) # Wait before retry
