import logging
import time
import os

class GeminiWebAgent:
    def __init__(self, browser_agent):
        self.browser = browser_agent

    def generate_prompts(self, video_data_list):
        logging.info("Generating prompts on Gemini...")
        prompts = []
        try:
             page = self.browser.page
             self.browser.navigate("https://gemini.google.com")

             try:
                 page.click("button:has-text('I agree')", timeout=5000)
             except:
                 pass

             for data in video_data_list:
                 try:
                      image_path = data.get("image_path")
                      if image_path and os.path.exists(image_path):
                           page.set_input_files("input[type='file']", image_path)
                           time.sleep(2)
                 except Exception as e:
                      logging.warning(f"Could not upload image to Gemini: {e}")

                 prompt_text = (
                     "Gambar ini adalah frame dari video affiliate tiktok. "
                     "Saya ingin membuat video seperti trend affiliate ini. "
                     "Sebutkan produknya dari gambar ini, dan berikan 3 prompt untuk Veo 3 yang memiliki kamera shot berbeda namun estetik. "
                     "Berikan respons DALAM FORMAT JSON SAJA (tanpa markdown lain) dengan struktur:\n"
                     '{"product": "nama produk", "prompts": ["prompt 1", "prompt 2", "prompt 3"]}'
                 )

                 try:
                     textarea = page.locator("rich-textarea, div[contenteditable='true']").first
                     textarea.fill(prompt_text)
                     page.keyboard.press("Enter")
                 except Exception as e:
                     logging.error(f"Failed to fill prompt: {e}")
                     continue

                 logging.info("Prompt sent. Waiting for Gemini response...")
                 page.wait_for_timeout(15000)

                 try:
                     response_elements = page.locator("message-content, .model-response-text").all()
                     if response_elements:
                         latest_response = response_elements[-1].inner_text()
                         import json
                         import re
                         match = re.search(r'\{.*\}', latest_response, re.DOTALL)
                         if match:
                             parsed = json.loads(match.group(0))
                             prompts.append({
                                 "product": parsed.get("product", "Unknown Product"),
                                 "prompts": parsed.get("prompts", []),
                                 "link": data.get("url"),
                                 "image_path": data.get("image_path")
                             })
                             logging.info("Successfully retrieved and parsed prompts from Gemini.")
                         else:
                             logging.warning("No JSON found in Gemini response.")
                 except Exception as e:
                     logging.error(f"Failed to read Gemini response: {e}")

        except Exception as e:
             logging.error(f"Error in GeminiWebAgent: {e}")
        return prompts

    def remove_background(self, image_path):
        logging.info(f"Removing background for {image_path} via Gemini Nano Banana...")
        try:
            page = self.browser.page
            self.browser.navigate("https://gemini.google.com")

            try:
                page.click("text='Nano Banana'", timeout=5000)
                logging.info("Activated Nano Banana mode.")
            except:
                logging.warning("Nano Banana menu not found.")

            try:
                if image_path and os.path.exists(image_path):
                     page.set_input_files("input[type='file']", image_path)
                     time.sleep(2)
            except Exception as e:
                 logging.warning(f"Could not upload image for BG removal: {e}")

            try:
                textarea = page.locator("rich-textarea, div[contenteditable='true']").first
                textarea.fill("remove beground dari foto yang saya kirimkan")
                page.keyboard.press("Enter")
            except Exception as e:
                logging.error(f"Failed to send background removal prompt: {e}")

            logging.info("Waiting for background removal...")
            page.wait_for_timeout(15000)

            try:
                # Implement actual background removal download logic
                logging.info("Attempting to locate and download processed image.")

                # Wait for response image
                img_elements = page.locator("message-content img").all()
                if img_elements:
                    latest_img = img_elements[-1]
                    img_src = latest_img.get_attribute("src")

                    if img_src and img_src.startswith("http"):
                        # Download using Playwright's page context or requests if auth is not complex
                        bg_removed_path = f"no_bg_{os.path.basename(image_path)}"
                        # Simulate a click on download if there is a button, or fetch the src
                        try:
                            # Many times gemini has a download button on hover
                            download_btn = page.locator("button[aria-label='Download']").last
                            if download_btn.is_visible():
                                with page.expect_download(timeout=30000) as download_info:
                                    download_btn.click()
                                download = download_info.value
                                download.save_as(bg_removed_path)
                                logging.info(f"Successfully downloaded background-removed image: {bg_removed_path}")
                                return bg_removed_path
                        except:
                            pass

                        # Fallback to fetching the image using Playwright's download context
                        try:
                            # Start listening for the download we are about to trigger
                            with page.expect_download(timeout=30000) as download_info:
                                page.evaluate(f"""
                                    const link = document.createElement('a');
                                    link.href = '{img_src}';
                                    link.download = 'bg_removed.png';
                                    document.body.appendChild(link);
                                    link.click();
                                    document.body.removeChild(link);
                                """)
                            download = download_info.value
                            download.save_as(bg_removed_path)
                            logging.info(f"Triggered JS download and saved background-removed image: {bg_removed_path}")
                            return bg_removed_path
                        except Exception as dl_err:
                            logging.error(f"Fallback download failed: {dl_err}")
            except Exception as e:
                logging.warning(f"Failed to download background-removed image: {e}")

            return image_path

        except Exception as e:
            logging.error(f"Error removing background: {e}")
            return None

    def ask_mentor(self, prompt_text):
        """Treats gemini.google.com as a mentor to get advice or solutions."""
        logging.info("Consulting Gemini Mentor...")
        try:
            page = self.browser.page
            self.browser.navigate("https://gemini.google.com")

            try:
                page.click("button:has-text('I agree')", timeout=5000)
            except:
                pass

            try:
                textarea = page.locator("rich-textarea, div[contenteditable='true']").first
                textarea.fill(prompt_text)
                page.keyboard.press("Enter")
            except Exception as e:
                logging.error(f"Failed to send mentor prompt: {e}")
                return "Error sending prompt."

            logging.info("Waiting for mentor response...")
            page.wait_for_timeout(15000)

            try:
                response_elements = page.locator("message-content, .model-response-text").all()
                if response_elements:
                    latest_response = response_elements[-1].inner_text()
                    logging.info(f"Mentor advised: {latest_response[:100]}...")
                    return latest_response
            except Exception as e:
                logging.error(f"Failed to read mentor response: {e}")

        except Exception as e:
            logging.error(f"Error consulting mentor: {e}")
        return "Tidak dapat menghubungi mentor."

    def get_negotiation_advice(self, client_request):
        prompt = (
            "Saya adalah AI agent otonom yang bekerja sebagai freelancer. "
            f"Saya menerima permintaan klien berikut: '{client_request}'. "
            "Tolong bertindak sebagai mentor saya. Berikan saya saran negosiasi, "
            "apa yang harus saya katakan kepada klien, dan langkah-langkah teknis "
            "apa yang harus saya lakukan selanjutnya untuk menyelesaikan tugas ini."
        )
        return self.ask_mentor(prompt)

    def get_failure_advice(self, error_context):
        prompt = (
            "Mentor, saya telah mencoba memperbaiki kode ini sebanyak 7 kali namun "
            f"terus gagal. Error terakhir yang saya terima adalah: '{error_context}'. "
            "Tolong berikan arahan: apakah saya harus menyerah dan memberi tahu klien, "
            "atau apakah ada solusi spesifik yang terlewat oleh saya? Tolong berikan "
            "keputusan final dan instruksinya."
        )
        return self.ask_mentor(prompt)
