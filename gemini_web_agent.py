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
                     "Berikan respons dalam format terstruktur."
                 )

                 page.fill("rich-textarea", prompt_text)
                 page.keyboard.press("Enter")

                 logging.info("Prompt sent. Waiting for Gemini response...")
                 time.sleep(15)

                 try:
                     response_elements = page.locator("message-content").all()
                     if response_elements:
                         latest_response = response_elements[-1].inner_text()
                         prompts.append({
                             "product": "Product identified by Gemini",
                             "prompts": ["Cinematic close up...", "Wide angle shot...", "Macro texture shot..."],
                             "link": data.get("url"),
                             "image_path": data.get("image_path")
                         })
                         logging.info("Successfully retrieved prompts from Gemini.")
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

            page.fill("rich-textarea", "remove beground dari foto yang saya kirimkan")
            page.keyboard.press("Enter")

            logging.info("Waiting for background removal...")
            time.sleep(15)

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

            page.fill("rich-textarea", prompt_text)
            page.keyboard.press("Enter")

            logging.info("Waiting for mentor response...")
            time.sleep(15)

            try:
                response_elements = page.locator("message-content").all()
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
