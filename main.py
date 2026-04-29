import logging
import time
import gc
from datetime import datetime
import pytz

from database import DatabaseManager
from llm_client import LLMClient
from browser_agent import BrowserAgent
from tiktok_veo_workflow import TikTokVeoWorkflow
from freelance_workflow import FreelanceWorkflow
from sandbox_tester import SandboxTester
from resource_monitor import ResourceMonitor
from financial_module import FinancialModule

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent_orchestrator.log"),
        logging.StreamHandler()
    ]
)

def run_agent_cycle():
    """Executes a single, strictly sequential cycle of the agent workflows with self-healing isolation."""
    logging.info("--- Starting New Agent Cycle ---")
    db = DatabaseManager()
    finance = FinancialModule(db_path="agent_state.db")
    llm = LLMClient(api_keys=[]) # Will be populated by freelance workflow check
    browser = BrowserAgent()

    try:
        # Instantiate workflows
        freelance_wf = FreelanceWorkflow(browser, llm, db, finance)

        # 1. Freelance Platform Checks (Messenger Role) & API Keys
        freelance_wf.load_api_keys()

        logging.info("Executing Freelance Platform interactions...")
        freelance_wf.handle_freelance_platforms()

        # 2. Client Coding Task via GitHub and Jules
        client_id = "pelanggan_01"
        logging.info(f"Executing GitHub and Jules workflow for {client_id}...")
        generated_code = freelance_wf.manage_github_and_jules(client_id)

        if generated_code:
             logging.info(f"Running sandbox tests for {client_id}...")
             sandbox_tester = SandboxTester(db)
             success = sandbox_tester.test_and_monitor_code(client_id, generated_code, duration_minutes=15)
             if success:
                 finance.record_transaction("GitHub/Jules", "Task Completed", 50.0, f"Successful autonomous task delivery for {client_id}")
    except Exception as e:
        logging.error(f"Error isolated in Freelance workflow cycle: {e}")

    try:
        # Explicit memory clear between major workflow sections
        browser.quit()
    except:
        pass
    gc.collect()

    try:
        # 3. TikTok & Veo 3 Video Generation Workflow
        logging.info("Executing TikTok and Veo 3 Video Workflow...")
        # Re-initialize browser for next isolated phase
        browser = BrowserAgent()
        tiktok_veo_wf = TikTokVeoWorkflow(browser, llm, db, finance)

        if tiktok_veo_wf.analyze_and_download_tiktok_trends():
            if tiktok_veo_wf.generate_prompts_and_process_images():
                video_count = tiktok_veo_wf.generate_veo_videos_and_send_telegram()
                if video_count:
                    finance.record_transaction("TikTok Affiliate", "Videos Sent", 10.0, "Successful affiliate video generation sequence")

    except Exception as e:
        logging.error(f"Error isolated in TikTok Veo workflow cycle: {e}")

    finally:
        # Strict Exit Criteria: Clean up all resources
        logging.info("Executing end-of-cycle cleanup...")
        if browser:
            browser.quit()
        db.close()

        # Ensure explicit references are dropped so garbage collection works properly
        freelance_wf = None
        tiktok_veo_wf = None
        sandbox_tester = None
        browser = None
        llm = None
        db = None
        finance = None

        gc.collect()
        logging.info("--- Cycle Complete. Memory cleared. ---")

def is_us_business_hours():
    """Checks if the current time is between 09:00 and 15:00 EST."""
    est = pytz.timezone('US/Eastern')
    now_est = datetime.now(est)

    # Business hours threshold (09:00 to 15:00)
    if 9 <= now_est.hour < 15:
        return True
    return False

def main():
    """Main orchestration loop (18/7 cycle with dynamic timezone rest)."""
    logging.info("Nexus-DualBrain-AI Agent Started.")

    # 24/7 Continuous Loop for Full Autonomy
    while True:
        if is_us_business_hours():
             logging.info("Current time is within US business hours (09:00-15:00 EST). Entering 6-hour sleep mode to avoid bot detection.")
             # Fulfill user requirement to sleep during US peak hours
             time.sleep(6 * 3600) # 6 hours
             continue

        # Check resources before starting the cycle
        resource_monitor = ResourceMonitor()
        if not resource_monitor.is_safe_to_proceed():
            logging.warning("Hardware resources strained. Deferring agent cycle and entering micro-sleep.")
            time.sleep(600) # Sleep for 10 minutes and check again
            continue

        run_agent_cycle()

        # Hardware cooldown after a full cycle load
        rest_seconds = 7200 # Standard 2 hours cooldown
        logging.info(f"Hardware cooling phase. Sleeping for {rest_seconds} seconds...")
        # Reduced sleep purely for the sandbox testing phase of this refactor
        simulation_sleep = 5
        logging.info(f"SIMULATION: Sleeping {simulation_sleep}s instead of {rest_seconds}s for sandbox dev test.")
        time.sleep(simulation_sleep)

if __name__ == "__main__":
    main()
