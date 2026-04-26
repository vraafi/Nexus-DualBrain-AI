import logging
import time
import gc

from database import DatabaseManager
from llm_client import LLMClient
from browser_agent import BrowserAgent
from tiktok_veo_workflow import TikTokVeoWorkflow
from freelance_workflow import FreelanceWorkflow
from sandbox_tester import SandboxTester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent_orchestrator.log"),
        logging.StreamHandler()
    ]
)

def run_agent_cycle():
    """Executes a single, strictly sequential cycle of the agent workflows."""
    logging.info("--- Starting New Agent Cycle ---")
    db = DatabaseManager()
    llm = LLMClient(api_keys=[]) # Will be populated by freelance workflow check
    browser = BrowserAgent()

    try:
        # Instantiate workflows
        freelance_wf = FreelanceWorkflow(browser, llm, db)
        tiktok_veo_wf = TikTokVeoWorkflow(browser, llm, db)
        sandbox_tester = SandboxTester(db)

        # 1. Freelance Platform Checks (Messenger Role) & API Keys
        freelance_wf.check_and_request_api_keys()

        logging.info("Executing Freelance Platform interactions...")
        freelance_wf.handle_freelance_platforms()

        # 2. Client Coding Task via GitHub and Jules
        # Simulating finding a task for "pelanggan_01"
        client_id = "pelanggan_01"
        logging.info(f"Executing GitHub and Jules workflow for {client_id}...")
        coding_success = freelance_wf.manage_github_and_jules(client_id)

        if coding_success:
             logging.info(f"Running sandbox tests for {client_id}...")
             sandbox_tester.test_and_monitor_code(client_id, duration_minutes=15)

        # Explicit memory clear between major workflow sections
        browser.quit()
        gc.collect()

        # 3. TikTok & Veo 3 Video Generation Workflow
        logging.info("Executing TikTok and Veo 3 Video Workflow...")
        # Re-initialize browser for next isolated phase
        browser = BrowserAgent()
        tiktok_veo_wf.browser = browser # update reference

        if tiktok_veo_wf.analyze_and_download_tiktok_trends():
            if tiktok_veo_wf.generate_prompts_and_process_images():
                tiktok_veo_wf.generate_veo_videos_and_send_telegram()

    except Exception as e:
        logging.error(f"Critical error in agent cycle: {e}")
    finally:
        # Strict Exit Criteria: Clean up all resources
        logging.info("Executing end-of-cycle cleanup...")
        if browser:
            browser.quit()
        db.close()

        del freelance_wf
        del tiktok_veo_wf
        del sandbox_tester
        del browser
        del llm
        del db

        gc.collect()
        logging.info("--- Cycle Complete. Memory cleared. ---")

def main():
    """Main orchestration loop (18/7 cycle with 2-hour rest)."""
    logging.info("Nexus-DualBrain-AI Agent Started.")

    # Using a finite loop for testing, in real scenario this would be `while True:`
    # We will simulate 1 cycle followed by a short rest.
    test_mode_cycles = 1
    current_cycle = 0

    while current_cycle < test_mode_cycles:
        run_agent_cycle()
        current_cycle += 1

        if current_cycle < test_mode_cycles: # Don't sleep after the very last test cycle
            # Dynamic resting period to cool down low-spec hardware
            rest_seconds = 7200 # 2 hours = 7200 seconds
            logging.info(f"Hardware cooling phase. Sleeping for {rest_seconds} seconds...")
            time.sleep(rest_seconds)

    logging.info("Agent process terminated gracefully.")

if __name__ == "__main__":
    main()
