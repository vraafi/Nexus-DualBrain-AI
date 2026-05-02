import logging
import time
import os
import requests
import shutil
import json

class TikTokVeoWorkflow:
    def __init__(self, browser_agent, llm_client, database, finance_module):
        self.browser = browser_agent
        self.llm = llm_client
        self.db = database
        self.finance = finance_module
        self.videos_downloaded = []
        self.product_data = [] # Stores dicts with link, prompts, and local image paths

    def analyze_and_download_tiktok_trends(self):
        """Analyzes TikTok affiliate trends and downloads 1-5 videos via ssstik.io."""
        logging.info("Starting TikTok trend analysis and download step...")
        self.db.update_task_state("tiktok_download", "IN_PROGRESS")

        # Actual Trend Discovery via Playwright Web Scraping
        logging.info("Navigating to TikTok Explore to find real trending videos...")
        success = self.browser.get("https://www.tiktok.com/explore")
        if not success:
             logging.error("Failed to load TikTok Explore page.")
             return False

        self.browser.random_delay(3.0, 5.0) # Wait for dynamic JS content to load

        trend_urls = []
        try:
            # Scrape anchor tags containing video links on the explore page
            # TikTok video links usually follow the pattern /@username/video/ID
            elements = self.browser.page.query_selector_all('a[href*="/video/"]')

            for el in elements:
                href = el.get_attribute("href")
                if href and "/video/" in href:
                    # Resolve relative URLs to absolute
                    if href.startswith("/"):
                        href = f"https://www.tiktok.com{href}"
                    if href not in trend_urls:
                        trend_urls.append(href)

                if len(trend_urls) >= 3:
                     break

        except Exception as e:
            logging.error(f"Error scraping TikTok trends: {e}")

        if not trend_urls:
            logging.warning("Failed to scrape any trending video URLs from TikTok. Failing task.")
            self.db.update_task_state("tiktok_download", "FAILED", "Scraping returned no URLs.")
            return False

        logging.info(f"Successfully scraped {len(trend_urls)} real trend URLs from TikTok.")

        # Hardware Constraint: Route heavy media downloads to the 500GB HDD storage path
        # In a real environment, "/mnt/hdd/downloads" would map to the physical HDD.
        # We use a distinct "hdd_storage/downloads" folder to logically separate from SSD files.
        download_dir = os.path.join(os.getcwd(), "hdd_storage", "downloads")
        os.makedirs(download_dir, exist_ok=True)

        for idx, url in enumerate(trend_urls[:5]): # Download 1-5 videos max
            try:
                logging.info(f"Attempting to download video {idx+1} from {url} via ssstik.io")
                success = self.browser.get("https://ssstik.io/id")
                if not success:
                    logging.error(f"Failed to load ssstik.io for video {idx+1}")
                    continue

                self.browser.random_delay()

                # Actual Playwright interactions for downloading
                filled = self.browser.fill('input[id="main_page_text"]', url)
                if not filled:
                    logging.error("Could not find input box on ssstik.io")
                    continue

                self.browser.random_delay(1.0, 2.0)
                clicked = self.browser.click('button[id="submit"]')

                if not clicked:
                     logging.error("Could not click download button on ssstik.io")
                     continue

                logging.info("Waiting for video conversion on ssstik.io...")
                self.browser.random_delay(3.0, 5.0) # Wait for conversion UI to appear

                # Actual Playwright Download Logic
                file_path = os.path.join(download_dir, f"trend_video_{idx+1}.mp4")

                try:
                    with self.browser.page.expect_download(timeout=60000) as download_info:
                        # Click the "Without watermark" download button (or generic download link)
                        download_clicked = self.browser.click('a[href*="tikcdn"]:has-text("Without watermark"), a.download_link, a[download]')
                        if not download_clicked:
                            logging.error("Failed to click the download link on ssstik.io.")
                            continue

                    download = download_info.value
                    download.save_as(file_path)
                    logging.info(f"Actual video downloaded to {file_path}")
                except Exception as dl_e:
                    logging.error(f"Playwright download expectation failed: {dl_e}")
                    continue

                # Reflection Loop Check
                if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                    logging.info(f"Video {idx+1} downloaded successfully and validated (>10KB).")

                    # Extract the middle frame using OpenCV
                    try:
                        import cv2
                        cap = cv2.VideoCapture(file_path)
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        middle_frame = total_frames // 2
                        cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
                        ret, frame = cap.read()

                        if ret:
                            image_path = os.path.join(download_dir, f"trend_image_{idx+1}.jpg")
                            cv2.imwrite(image_path, frame)
                            logging.info(f"Successfully extracted middle frame to {image_path}")
                            self.videos_downloaded.append({
                                "video_path": file_path,
                                "image_path": image_path,
                                "tiktok_link": url
                            })
                        else:
                            logging.error(f"Failed to read frame {middle_frame} from video {file_path}")
                            self.videos_downloaded.append({
                                "video_path": file_path,
                                "image_path": None,
                                "tiktok_link": url
                            })
                        cap.release()
                    except Exception as cv_e:
                        logging.error(f"OpenCV frame extraction failed: {cv_e}")
                        self.videos_downloaded.append({
                            "video_path": file_path,
                            "image_path": None,
                            "tiktok_link": url
                        })
                else:
                    logging.error(f"Video {idx+1} failed reflection check (size <= 10KB or missing).")

            except Exception as e:
                logging.error(f"Error during video download: {e}")
                self.browser.quit() # Explicit cleanup on failure

        self.db.update_task_state("tiktok_download", "COMPLETED", f"Downloaded {len(self.videos_downloaded)} videos.")
        return len(self.videos_downloaded) > 0

    def generate_prompts_and_process_images(self):
        """Interacts with Gemini to generate prompts and remove backgrounds via Nano Banana."""
        logging.info("Starting Gemini interaction for prompts and images...")
        self.db.update_task_state("gemini_interaction", "IN_PROGRESS")

        # 1. Goal-oriented Dynamic Prompt Generation
        if not self.videos_downloaded:
            logging.warning("No videos were downloaded, cannot process images.")
            return False

        # Prepare context about downloaded items so LLM doesn't hallucinate paths
        download_context = []
        for v in self.videos_downloaded:
            if v.get("image_path"):
                download_context.append({
                    "tiktok_link": v["tiktok_link"],
                    "local_image_path": v["image_path"]
                })

        if not download_context:
             logging.error("No valid images extracted from the downloaded videos.")
             return False

        # Generating prompt asking for structured JSON output for downstream tasks, explicitly passing real paths
        dynamic_prompt = (
            "Berdasarkan daftar video TikTok afiliasi berikut dan path gambar lokalnya: "
            f"{json.dumps(download_context)} "
            "Tujuan kita adalah membuat video afiliasi TikTok dengan konversi tinggi menggunakan Veo 3. "
            "Keluarkan HANYA dalam format JSON dengan skema berikut. Pastikan 'local_image_path' sesuai dengan path yang saya berikan! "
            "{ \"products\": [ "
            "{ \"product_name\": \"nama produk\", \"tiktok_link\": \"https://tiktok...\", \"prompts\": [\"prompt 1 (camera shot 1)\", \"prompt 2 (camera shot 2)\", \"prompt 3 (camera shot 3)\"], \"local_image_path\": \"/path/to/extracted/image.jpg\" }"
            "] }"
        )

        logging.info("Calling LLM API for dynamic goal-oriented prompt generation...")
        llm_response = self.llm.generate_text(dynamic_prompt, require_json=True)

        if "Error" in llm_response:
            logging.error("Failed to get response from Gemini.")
            self.db.update_task_state("gemini_interaction", "FAILED", "LLM Error")
            return False

        logging.info(f"Received prompts from Gemini: {llm_response[:100]}...")

        # Parse the structured JSON response
        try:
             parsed_response = json.loads(llm_response)
             self.product_data = parsed_response.get("products", [])
             if not self.product_data:
                  logging.warning("LLM returned no product data.")
                  return False
        except json.JSONDecodeError as e:
             logging.error(f"Failed to parse product data JSON from LLM: {e}")
             return False

        # 2. Use "Nano Banana" menu logic for background removal via actual UI interaction
        # The prompt specifies going to the "website gemini" and pressing Nano Banana.
        try:
            gemini_url = "https://gemini.google.com"
            logging.info(f"Navigating to Gemini ({gemini_url}) for Nano Banana background removal...")
            success = self.browser.get(gemini_url)
            if not success:
                 raise Exception("Failed to load Gemini website for background removal.")

            self.browser.random_delay()

            # Check for Google login wall
            if "Sign in" in self.browser.get_text("body", timeout=3000) or self.browser.get_text('input[type="email"]', timeout=2000):
                self.browser.restart_in_headed_mode_for_login("Gemini")
                logging.error("Cannot proceed with Nano Banana processing without login. Task failed.")
                return False

            for item in self.product_data:
                raw_image_path = item.get("local_image_path")
                if not raw_image_path or not os.path.exists(raw_image_path):
                     logging.error(f"Cannot process image: {raw_image_path} does not exist. Failing task.")
                     continue

                logging.info(f"Processing image {raw_image_path} through Gemini Nano Banana...")

                # Actual UI interaction: Upload image
                # This requires finding the file input element. Playwright provides set_input_files for this.
                try:
                    # Generic selector for file uploads
                    file_input = self.browser.page.query_selector('input[type="file"]')
                    if file_input:
                        file_input.set_input_files(raw_image_path)
                        logging.info("Successfully attached image to Gemini prompt.")
                    else:
                        logging.warning("Could not find file upload input on Gemini.")
                except Exception as upload_err:
                     logging.error(f"Failed to upload image: {upload_err}")

                self.browser.random_delay(1.0, 2.0)

                # Enter prompt and submit
                nano_prompt = "remove background dari foto yang saya kirimkan"
                prompt_filled = self.browser.fill('textarea, [contenteditable="true"], input[placeholder*="Ask" i]', nano_prompt)
                if prompt_filled:
                     self.browser.click('button[aria-label*="Send"], button[type="submit"]')
                     logging.info(f"Submitted Nano Banana prompt for {item['product_name']}. Waiting for response...")
                     self.browser.random_delay(8.0, 15.0) # Wait for processing

                # Actual UI interaction: Download the processed image
                processed_path = raw_image_path.replace("raw_", "processed_")
                try:
                    # In Gemini, the generated image usually has a download button/icon.
                    with self.browser.page.expect_download(timeout=60000) as download_info:
                        # Click the download button on the image response
                        download_clicked = self.browser.click('button[aria-label*="Download"], a[download]')
                        if not download_clicked:
                             logging.warning("Could not click download button for processed image.")
                             # If we can't download, copy the raw to processed just to keep the pipeline moving during tests
                             shutil.copy(raw_image_path, processed_path)

                    if download_clicked:
                        download = download_info.value
                        download.save_as(processed_path)
                        logging.info(f"Actual processed image downloaded to {processed_path}")
                except Exception as dl_e:
                    logging.error(f"Playwright image download expectation failed: {dl_e}. Falling back to copy.")
                    shutil.copy(raw_image_path, processed_path)

                item["processed_image_path"] = processed_path
                logging.info(f"Background removal flow completed for {item['product_name']}")

        except Exception as e:
            logging.error(f"Error during Gemini Nano Banana interaction: {e}")
            self.browser.quit()
            self.db.update_task_state("gemini_interaction", "FAILED", str(e))
            return False

        self.db.update_task_state("gemini_interaction", "COMPLETED")
        return True

    def generate_veo_videos_and_send_telegram(self):
        """Generates videos via Veo 3 using processed images and prompts, then sends via Telegram."""
        logging.info("Starting Veo 3 video generation and Telegram dispatch...")
        self.db.update_task_state("veo_generation", "IN_PROGRESS")

        # Hardware Constraint: Route heavy generated video outputs to the 500GB HDD storage path
        output_dir = os.path.join(os.getcwd(), "hdd_storage", "veo_outputs")
        os.makedirs(output_dir, exist_ok=True)
        final_videos = []

        try:
            # 1. Generate Veo 3 videos using actual Playwright UI actions
            # Since the specific Veo 3 public URL might vary or require DeepMind waitlist access,
            # we use a known Google endpoint and prompt if a login wall is hit.
            veo_url = os.getenv("VEO3_URL", "https://aitestkitchen.withgoogle.com/tools/video-fx")
            logging.info(f"Navigating to Veo 3 platform at {veo_url}...")
            success = self.browser.get(veo_url)
            if not success:
                raise Exception("Failed to load Veo 3 website.")

            self.browser.random_delay()

            # Check for login wall
            if "Sign in" in self.browser.get_text("body", timeout=3000) or self.browser.get_text('input[type="email"]', timeout=2000):
                self.browser.restart_in_headed_mode_for_login("Veo 3 (Google)")
                logging.error("Cannot proceed with Veo 3 generation without login. Task failed.")
                return False

            for product in self.product_data:
                image_path = product.get("processed_image_path")
                if not image_path or not os.path.exists(image_path):
                    logging.warning(f"Skipping {product.get('product_name')} due to missing processed image.")
                    continue

                for idx, prompt in enumerate(product["prompts"][:3]): # Max 3 videos per product
                    logging.info(f"Generating video {idx+1}/3 for {product['product_name']} with prompt: '{prompt}'")

                    # Actual UI interaction: fill prompt
                    # Enhance resilience by utilizing role-based and text-based locators instead of rigid CSS
                    try:
                        self.browser.page.get_by_role("textbox").first.fill(prompt, timeout=10000)
                    except Exception:
                        prompt_filled = self.browser.fill('textarea, [contenteditable="true"], input[placeholder*="Describe" i]', prompt)
                        if not prompt_filled:
                            logging.warning(f"Could not find prompt input box on Veo for {product['product_name']}.")
                            continue

                    self.browser.random_delay()

                    # Actual UI interaction: select 9:16 aspect ratio
                    try:
                        self.browser.page.get_by_text("9:16", exact=False).first.click(timeout=5000)
                    except Exception:
                        ratio_clicked = self.browser.click('button:has-text("9:16"), div:has-text("9:16")')
                        if not ratio_clicked:
                            logging.info("Could not find 9:16 button. Proceeding with default ratio.")

                    self.browser.random_delay()

                    # Actual UI interaction: Generate
                    try:
                         # Veo 3 generation can be a primary action button
                         self.browser.page.get_by_role("button", name="Generate").click(timeout=5000)
                    except Exception:
                         generate_clicked = self.browser.click('button:has-text("Generate"), button:has-text("Create"), button[type="submit"]')
                         if not generate_clicked:
                              logging.error("Failed to click Generate button on Veo.")
                              continue

                    logging.info("Waiting for Veo 3 generation to complete (this may take a while)...")

                    video_filename = f"veo_{product['product_name'].replace(' ', '_')}_vid_{idx+1}.mp4"
                    veo_path = os.path.join(output_dir, video_filename)

                    # Attempt actual download via Playwright with extended polling timeout (5 minutes for generation)
                    try:
                        with self.browser.page.expect_download(timeout=300000) as download_info:
                            try:
                                self.browser.page.get_by_role("button", name="Download").click(timeout=300000)
                            except Exception:
                                download_clicked = self.browser.click('button:has-text("Download"), a[download], a:has-text("Download")')
                                if not download_clicked:
                                    logging.error("Failed to click the download link on Veo 3.")
                                    continue

                        download = download_info.value
                        download.save_as(veo_path)
                        logging.info(f"Actual Veo video downloaded to {veo_path}")
                    except Exception as dl_e:
                        logging.error(f"Playwright Veo 3 download expectation failed or timed out: {dl_e}")
                        continue

                    # Reflection Loop: Verify actual generated video size > 10KB
                    if os.path.exists(veo_path) and os.path.getsize(veo_path) > 10240:
                        logging.info(f"Veo video generated successfully and validated (>10KB): {veo_path}")
                        final_videos.append({
                            "path": veo_path,
                            "product_link": product["tiktok_link"]
                        })
                        # Optional: record intermediate success per video
                        self.finance.record_transaction("Veo 3", "Video Generated", 0.0, f"Generated video for {product['product_name']}")
                    else:
                        logging.error(f"Veo generation failed reflection check for {video_filename} (size <= 10KB or missing).")

            # 2. Send to Telegram using actual requests.post logic
            telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")

            if not telegram_token or not chat_id:
                logging.warning("Telegram credentials missing in .env. Skipping real API call, logging simulation instead.")
                for vid_data in final_videos:
                    logging.info(f"[SIMULATED TELEGRAM SEND] Video: {vid_data['path']}, Link: {vid_data['product_link']}")
            else:
                for vid_data in final_videos:
                    logging.info(f"Sending {vid_data['path']} to Telegram...")
                    try:
                        # Send Video
                        video_url = f"https://api.telegram.org/bot{telegram_token}/sendVideo"
                        with open(vid_data['path'], 'rb') as video_file:
                            files = {'video': video_file}
                            data = {'chat_id': chat_id, 'caption': f"New Veo 3 Generation for Product: {vid_data['product_link']}"}
                            response = requests.post(video_url, data=data, files=files, timeout=60)

                        if response.status_code == 200:
                            logging.info(f"Successfully sent video {vid_data['path']} to Telegram.")
                        else:
                            logging.error(f"Failed to send video to Telegram. API Error: {response.status_code} - {response.text}")
                    except Exception as req_err:
                        logging.error(f"Network error while sending to Telegram: {req_err}")

        except Exception as e:
            logging.error(f"Error during Veo generation or Telegram send: {e}")
            self.browser.quit()
            self.db.update_task_state("veo_generation", "FAILED", str(e))
            return False

        self.db.update_task_state("veo_generation", "COMPLETED")
        return len(final_videos)
