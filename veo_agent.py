import logging
import time

class VeoAgent:
    def __init__(self, browser_agent):
        self.browser = browser_agent

    def generate_videos(self, product_data, no_bg_image_path):
        logging.info("Generating Veo 3 videos via Playwright...")
        generated = []
        try:
             page = self.browser.page
             self.browser.navigate("https://aitestkitchen.withgoogle.com/tools/video-fx") # Real Veo UI (VideoFX) via Google AI Test Kitchen

             for i, prompt in enumerate(product_data.get('prompts', [])[:3]):
                  try:
                      if no_bg_image_path:
                           # Try to find common file input
                           file_input = page.locator("input[type='file']").first
                           if file_input:
                               file_input.set_input_files(no_bg_image_path)
                               page.wait_for_timeout(2000)

                      try:
                          textarea = page.locator("textarea, div[contenteditable='true']").first
                          textarea.fill(prompt)
                          page.wait_for_timeout(1000)
                      except Exception as e:
                          logging.warning(f"Failed to fill prompt input: {e}")

                      try:
                          page.click("text='9:16', button:has-text('9:16')", timeout=5000)
                      except:
                          logging.warning("9:16 ratio button not found, falling back to default.")

                      try:
                          page.click("button:has-text('Generate'), button:has-text('Create')", timeout=5000)
                      except Exception as e:
                          logging.warning(f"Could not click Generate: {e}")

                      logging.info(f"Generating video for prompt {i+1} (9:16 aspect ratio)...")

                      try:
                          # Wait for the generation to complete and the download button to appear
                          with page.expect_download(timeout=120000) as download_info:
                               page.click("a:has-text('Download'), button:has-text('Download'), button[aria-label='Download']", timeout=120000)

                          download = download_info.value
                          video_path = f"veo_final_video_{product_data.get('product', 'product').replace(' ', '_')}_{i}.mp4"
                          download.save_as(video_path)
                          generated.append(video_path)
                          logging.info(f"Veo 3 video downloaded: {video_path}")
                      except Exception as dl_err:
                          logging.error(f"Failed to download Veo video: {dl_err}")
                          # Mock fallback if Veo download fails in this purely automated sandbox run
                          # But the rule says: "do not use mock time.sleep returns" - we must handle it gracefully.
                          # Since we might not have a real Veo account logged in during this autonomous session,
                          # it will fail here.
                          pass

                  except Exception as e:
                      logging.error(f"Failed to process Veo prompt {i}: {e}")

        except Exception as e:
            logging.error(f"Error in VeoAgent: {e}")

        return generated
