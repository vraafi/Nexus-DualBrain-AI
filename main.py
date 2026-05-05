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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SLEEP_DURATION = 7200 # 2 hours resting period to cool down

def run_workflow():
    api_keys = [os.environ.get(f"GEMINI_KEY_{i}", f"mock_key_{i}") for i in range(1, 11)]
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
            save_state(task_id, "RUNNING", "freelance_job_hunt_phase", {})
            brand_context = branding.get_branding_strategy("upwork")

            with BrowserAgent(headless=False) as browser:
                freelance = FreelanceAgent(browser, llm)
                login_success = freelance.login_upwork()
                if not login_success:
                    telegram.send_message("WARNING: Upwork Login Failed or Needs Manual Captcha.")
                    # Continue anyway to scrape public jobs

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
            # Step 3: Sandbox Testing with Infinite Self-Correction Loop
            # The variable code_path may not be available if resuming directly into this step,
            # so we check if the file exists from a previous run or skip.
            if 'code_path' not in locals():
                code_path = "generated_script.py"

            if code_path and os.path.exists(code_path):
                save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})
                sandbox_result = sandbox.test_code(code_path)
                if not sandbox_result:
                    raise Exception("Sandbox testing failed completely after 7 retries and mentor cancellation.")
            else:
                raise Exception("No code path returned from Jules or missing. Skipping sandbox.")
            current_step = "delivery_phase"

        if current_step == "delivery_phase":
            # Step 4: Submit Proposal & Deliver to Client natively
            save_state(task_id, "RUNNING", "delivery_phase", {"job_data": job_data})
            if not job_data:
                 state = load_state(task_id)
                 job_data = state.get("data", {}).get("job_data")

            if os.path.exists(code_path) and job_data:
                # Log financial start
                finance.log_proposal("upwork", job_data.get('title', 'Unknown Job'), expected_revenue=50.0)

                with BrowserAgent(headless=False) as browser:
                    freelance = FreelanceAgent(browser, llm)
                    brand_context = branding.get_branding_strategy("upwork")

                    # Submit Proposal
                    proposal_success = freelance.submit_proposal(job_data, brand_context, code_path)

                    if proposal_success:
                        # Deliver
                        delivery_success = freelance.deliver_work(job_data, code_path)
                        if delivery_success:
                            finance.update_job_status(job_data.get('title'), "DELIVERED", actual_revenue=50.0)
                            telegram.send_message(f"Successfully Delivered Job: {job_data.get('title')}")
                        else:
                            telegram.send_message("Proposal submitted, but Delivery step failed.")
                    else:
                         telegram.send_message("Failed to submit proposal.")
            else:
                telegram.send_message("Task failed. Code path missing or job data lost.")

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
