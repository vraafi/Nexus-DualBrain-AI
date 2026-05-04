import logging
import requests

class TelegramAgent:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text):
        logging.info("Sending message to Telegram API...")
        try:
             requests.post(
                 f"{self.base_url}/sendMessage",
                 json={"chat_id": self.chat_id, "text": text}
             )
             return True
        except Exception as e:
             logging.error(f"Failed to send message to Telegram: {e}")
             return False

    def send_document(self, file_path, caption=""):
        logging.info(f"Sending document {file_path} to Telegram API...")
        try:
             with open(file_path, 'rb') as f:
                 requests.post(
                     f"{self.base_url}/sendDocument",
                     data={"chat_id": self.chat_id, "caption": caption},
                     files={"document": f}
                 )
             return True
        except Exception as e:
             logging.error(f"Failed to send document to Telegram: {e}")
             return False
