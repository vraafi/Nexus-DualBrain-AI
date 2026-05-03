import logging
import time
import os
import cv2

class TikTokAgent:
    def __init__(self, browser_agent):
        self.browser = browser_agent

    def extract_frame(self, video_path, output_image_path):
        """Uses OpenCV to extract the first frame of the video to send to Gemini/Veo."""
        logging.info(f"Extracting frame from {video_path} using OpenCV...")
        try:
            cap = cv2.VideoCapture(video_path)
            success, image = cap.read()
            if success:
                cv2.imwrite(output_image_path, image)
                logging.info(f"Saved frame to {output_image_path}")
                cap.release()
                return output_image_path
            cap.release()
        except Exception as e:
            logging.error(f"Error extracting frame: {e}")
        return None

    def analyze_trends(self):
        logging.info("Searching TikTok for affiliate trends...")
        urls = []
        try:
            page = self.browser.page
            self.browser.navigate("https://www.tiktok.com/search?q=tiktok+affiliate+racun")
            time.sleep(5)

            link_elements = page.locator("a[href*='/video/']").all()
            for elem in link_elements:
                href = elem.get_attribute("href")
                if href and href not in urls:
                    urls.append(href)
                    if len(urls) >= 5:
                        break

            logging.info(f"Found {len(urls)} trending videos.")
        except Exception as e:
             logging.error(f"Error in analyze_trends: {e}")
             urls = ["https://www.tiktok.com/@tiktok/video/7106594312292453678"]

        return urls

    def download_videos(self, urls):
        logging.info("Downloading videos via ssstik.io...")
        downloaded_data = []

        try:
             page = self.browser.page
             for i, url in enumerate(urls[:5]):
                 self.browser.navigate("https://ssstik.io/id")

                 page.fill("#main_page_text", url)
                 page.click("#submit")

                 try:
                     page.wait_for_selector("a.pure-button:has-text('Tanpa tanda air')", timeout=20000)

                     with page.expect_download(timeout=30000) as download_info:
                         page.click("a.pure-button:has-text('Tanpa tanda air')")

                     download = download_info.value
                     video_path = os.path.abspath(f"video_trend_{i}.mp4")
                     download.save_as(video_path)
                     logging.info(f"Downloaded: {video_path}")

                     # Extract frame for Veo/Gemini
                     image_path = os.path.abspath(f"frame_trend_{i}.jpg")
                     extracted_img = self.extract_frame(video_path, image_path)

                     downloaded_data.append({
                         "url": url,
                         "video_path": video_path,
                         "image_path": extracted_img
                     })

                 except Exception as e:
                     logging.error(f"Failed to download {url}: {e}")

        except Exception as e:
             logging.error(f"Error in TikTokAgent download: {e}")

        return downloaded_data
