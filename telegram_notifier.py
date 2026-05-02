import os
import requests
import logging

class TelegramNotifier:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def send_message(self, message):
        """Sends a text message to the user via Telegram."""
        if not self.bot_token or not self.chat_id:
            logging.debug("Telegram credentials not set. Simulating push notification: " + message)
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": f"🤖 *NEXUS AGI UPDATE*\n\n{message}",
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                logging.error(f"Failed to send Telegram notification: {response.text}")
                return False
        except Exception as e:
            logging.error(f"Network error sending Telegram notification: {e}")
            return False
