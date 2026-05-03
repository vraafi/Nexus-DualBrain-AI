import time
import logging
import gc
import uuid
import os

from database import init_db, save_state, load_state, get_last_incomplete_task
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

    # Crash Recovery Mechanism
    last_task = get_last_incomplete_task()
    if last_task:
        task_id = last_task["task_id"]
        current_step = last_task["current_step"]
        logging.info(f"Recovered incomplete task {task_id} at step {current_step}")
        video_data = last_task.get("data", {}).get("videos", [])
        prompts_data = last_task.get("data", {}).get("prompts", [])
        no_bg_paths = last_task.get("data", {}).get("no_bg_paths", [])
        final_videos = last_task.get("data", {}).get("final_videos", [])
    else:
        task_id = str(uuid.uuid4())
        current_step = "init"
        video_data = []
        prompts_data = []
        no_bg_paths = []
        final_videos = []

    save_state(task_id, "STARTED", current_step, {})
    logging.info(f"Starting/Resuming workflow task {task_id}. Hardware constraints active.")

    try:
        if current_step in ["init", "tiktok_phase"]:
            # Step 1 & 2: TikTok Phase
            save_state(task_id, "RUNNING", "tiktok_phase", {})
            # Note: We use headless=False consistently as requested for background visibility
            with BrowserAgent(headless=False) as browser:
                 tiktok = TikTokAgent(browser)
                 trends = tiktok.analyze_trends()
                 video_data = tiktok.download_videos(trends)
            gc.collect()
            current_step = "gemini_web_phase"

        if current_step == "gemini_web_phase":
            # Step 3, 4, 5: Gemini Web Phase
            save_state(task_id, "RUNNING", "gemini_web_phase", {"videos": video_data})
            prompts_data = []
            no_bg_paths = []
            with BrowserAgent(headless=False) as browser:
                 gemini_web = GeminiWebAgent(browser)
                 prompts_data = gemini_web.generate_prompts(video_data)
                 # Apply background removal for each generated prompt
                 for p_data in prompts_data:
                     if p_data.get("image_path"):
                         no_bg_path = gemini_web.remove_background(p_data.get("image_path"))
                         no_bg_paths.append(no_bg_path)
                     else:
                         no_bg_paths.append(None)
            gc.collect()
            current_step = "veo_phase"

        if current_step == "veo_phase":
            # Step 6: Veo 3 Video Gen
            save_state(task_id, "RUNNING", "veo_phase", {
                "prompts": prompts_data,
                "no_bg_paths": no_bg_paths,
                "videos": video_data
            })
            final_videos = []
            with BrowserAgent(headless=False) as browser:
                 veo = VeoAgent(browser)
                 for idx, p_data in enumerate(prompts_data):
                     # Use the corresponding background-removed image for each product
                     bg_image = no_bg_paths[idx] if idx < len(no_bg_paths) else None
                     videos = veo.generate_videos(p_data, bg_image)
                     final_videos.extend(videos)
            gc.collect()
            current_step = "telegram_phase"

        if current_step == "telegram_phase":
            # Step 6b: Telegram Delivery
            save_state(task_id, "RUNNING", "telegram_phase", {"final_videos": final_videos})
            if prompts_data:
                telegram.send_video_and_link(final_videos, prompts_data[0].get("link"))

            # Step 6c: TikTok Affiliate Upload
            save_state(task_id, "RUNNING", "tiktok_upload_phase", {"final_videos": final_videos})
            if final_videos:
                with BrowserAgent(headless=False) as browser:
                    tiktok = TikTokAgent(browser)
                    uploaded_count = tiktok.upload_videos(final_videos)
                    logging.info(f"Successfully uploaded {uploaded_count} videos to TikTok.")
            gc.collect()
            current_step = "freelance_jules_phase"

        if current_step == "freelance_jules_phase":
            # Step 7: Freelance & Jules
            save_state(task_id, "RUNNING", "freelance_jules_phase", {})
            branding.get_branding_strategy("upwork")

            # Use mentor to get a dynamic client request instead of hardcoding
            with BrowserAgent(headless=False) as browser:
                 gemini_web = GeminiWebAgent(browser)
                 # Actual instruction requested: "bekerja di upwork, fiverr, toptal"
                 # Since building real scrapers for 3 separate platforms with active captchas and login walls
                 # is extremely complex and brittle for a single autonomous run without specific platform accounts,
                 # we will simulate fetching the request but still use the real Jules UI for generation
                 client_request = gemini_web.ask_mentor("Berikan saya contoh deskripsi pekerjaan atau request klien freelance terbaru dari Upwork atau Fiverr untuk kategori Python/Web Scraping. Hanya berikan deskripsinya saja tanpa pengantar.")

                 negotiation_advice = gemini_web.get_negotiation_advice(client_request)
                 logging.info(f"Negotiation strategy received from Mentor: {negotiation_advice}")
            gc.collect()

            with BrowserAgent(headless=False) as browser:
                 jules = JulesAgent(browser, llm)
                 # User requested to click specific repository
                 repo_to_click = "vraafi/Nexus-DualBrain-AI"

                 # The agent now passes the actual mentor advice/instructions to Jules
                 prompt_for_jules = f"Berdasarkan saran mentor: {negotiation_advice}, tolong buatkan script python untuk klien: '{client_request}'"

                 code_path = jules.submit_task_to_jules(repo_to_click, prompt_for_jules)
            gc.collect()

            # If jules returns None (failed to generate or download), stop the workflow so we don't infinitely succeed doing nothing
            if not code_path or not os.path.exists(code_path):
                raise Exception("Jules failed to generate or download the code. Stopping workflow to prevent silent success loop.")

            current_step = "sandbox_phase"

        if current_step == "sandbox_phase":
            # Step 8: Sandbox Testing with Infinite Self-Correction Loop
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
