import logging
import time
import os

class GeminiWebAgent:
    def __init__(self, browser_agent):
        self.browser = browser_agent

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
