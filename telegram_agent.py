import logging
import requests

class TelegramAgent:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_video_and_link(self, video_paths, product_link):
        logging.info("Sending results to Telegram API...")

        try:
             # Send text message with link
             requests.post(
                 f"{self.base_url}/sendMessage",
                 json={"chat_id": self.chat_id, "text": f"Here are the Veo 3 videos for product link: {product_link}"}
             )

             # Send actual video files
             for video in video_paths:
                  logging.info(f"Sending video {video} to chat {self.chat_id}")
                  with open(video, 'rb') as f:
                      requests.post(f"{self.base_url}/sendVideo", data={"chat_id": self.chat_id}, files={"video": f})
             return True
        except Exception as e:
             logging.error(f"Failed to send to Telegram: {e}")
             return False
