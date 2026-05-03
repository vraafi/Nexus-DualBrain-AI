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
             self.browser.navigate("https://deepmind.google/technologies/veo/") # Assuming Veo UI URL

             # User Instructions:
             # 6. Input image, input prompts, select 9:16 aspect ratio, generate 3 videos per product.

             for i, prompt in enumerate(product_data.get('prompts', [])[:3]):
                  try:
                      # Wait for the image upload input to be ready
                      if no_bg_image_path:
                           page.set_input_files("input[type='file']", no_bg_image_path)
                           time.sleep(2)

                      # Fill the prompt
                      page.fill("textarea", prompt)
                      time.sleep(1)

                      # Select 9:16 aspect ratio (assuming a button or dropdown)
                      try:
                          page.click("text='9:16'", timeout=5000)
                      except:
                          logging.warning("9:16 ratio button not found, falling back to default.")

                      # Click Generate
                      page.click("button:has-text('Generate')", timeout=5000)

                      logging.info(f"Generating video for prompt {i+1} (9:16 aspect ratio)...")

                      # Wait for the generation to complete and the download button to appear
                      # Assuming Veo 3 takes ~30-60s to generate
                      with page.expect_download(timeout=120000) as download_info:
                           page.click("a:has-text('Download'), button:has-text('Download')", timeout=120000)

                      download = download_info.value
                      video_path = f"veo_final_video_{i}.mp4"
                      download.save_as(video_path)
                      generated.append(video_path)
                      logging.info(f"Veo 3 video downloaded: {video_path}")

                  except Exception as e:
                      logging.error(f"Failed to generate Veo video for prompt {i}: {e}")

        except Exception as e:
            logging.error(f"Error in VeoAgent: {e}")

        return generated
