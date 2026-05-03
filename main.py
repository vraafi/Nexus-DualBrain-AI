import time
import logging
import gc
import uuid
import os

from database import init_db, save_state, load_state
from browser_agent import BrowserAgent
from tiktok_agent import TikTokAgent
from gemini_web_agent import GeminiWebAgent
from veo_agent import VeoAgent
from telegram_agent import TelegramAgent
from jules_agent import JulesAgent
from freelance_branding import FreelanceBranding
from sandbox_tester import SandboxTester
from api_client import GeminiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SLEEP_DURATION = 7200 # 2 hours resting period to cool down

def run_workflow():
    api_keys = [os.environ.get(f"GEMINI_KEY_{i}", f"mock_key_{i}") for i in range(1, 11)]
    llm = GeminiClient(api_keys)
    telegram = TelegramAgent("mock_token", "mock_chat_id")
    branding = FreelanceBranding()
    sandbox = SandboxTester(duration_minutes=15, llm_client=llm)

    task_id = str(uuid.uuid4())
    save_state(task_id, "STARTED", "init", {})
    logging.info(f"Starting workflow task {task_id}. Hardware constraints active.")

    try:
        # Step 1 & 2: TikTok Phase
        save_state(task_id, "RUNNING", "tiktok_phase", {})
        # Note: We use headless=False consistently as requested for background visibility
        with BrowserAgent(headless=False) as browser:
             tiktok = TikTokAgent(browser)
             trends = tiktok.analyze_trends()
             video_data = tiktok.download_videos(trends)
        gc.collect()

        # Step 3, 4, 5: Gemini Web Phase
        save_state(task_id, "RUNNING", "gemini_web_phase", {"videos": video_data})
        prompts_data = []
        no_bg_paths = []
        with BrowserAgent(headless=False) as browser:
             gemini_web = GeminiWebAgent(browser)
             prompts_data = gemini_web.generate_prompts(video_data)
             if prompts_data and prompts_data[0].get("image_path"):
                 no_bg_paths.append(gemini_web.remove_background(prompts_data[0].get("image_path")))
        gc.collect()

        # Step 6: Veo 3 Video Gen
        save_state(task_id, "RUNNING", "veo_phase", {"prompts": prompts_data})
        final_videos = []
        with BrowserAgent(headless=False) as browser:
             veo = VeoAgent(browser)
             for p_data in prompts_data:
                 videos = veo.generate_videos(p_data, no_bg_paths[0] if no_bg_paths else None)
                 final_videos.extend(videos)
        gc.collect()

        # Step 6b: Telegram Delivery
        save_state(task_id, "RUNNING", "telegram_phase", {"final_videos": final_videos})
        if prompts_data:
            telegram.send_video_and_link(final_videos, prompts_data[0].get("link"))

        # Step 7: Freelance & Jules
        save_state(task_id, "RUNNING", "freelance_jules_phase", {})
        branding.get_branding_strategy("upwork")

        with BrowserAgent(headless=False) as browser:
             jules = JulesAgent(browser, llm)
             # User requested to click specific repository
             repo_to_click = "vraafi/Nexus-DualBrain-AI"
             code_path = jules.submit_task_to_jules(repo_to_click, "Create an AI orchestration script.")
        gc.collect()

        # Step 8: Sandbox Testing with Infinite Self-Correction Loop
        if code_path and os.path.exists(code_path):
            save_state(task_id, "RUNNING", "sandbox_phase", {"code": code_path})
            sandbox.test_code(code_path)
        else:
            logging.warning("No code path returned from Jules. Skipping sandbox.")

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

    # Run once for testing
    run_workflow()
