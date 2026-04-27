import requests
import json
import logging
import os

class LLMClient:
    def __init__(self, api_keys, model="gemma-4-31b-it"):
        if not api_keys:
            logging.warning("No API keys provided.")
            self.api_keys = []
        else:
            self.api_keys = api_keys
        self.model = model
        self.current_key_index = 0
        self.key_usage_counts = {key: 0 for key in self.api_keys}
        self.MAX_CALLS_PER_KEY = 1000 # Configurable threshold to prevent bans

    def update_keys(self, new_keys):
        """Dynamically updates the keys and initializes usage tracking."""
        for key in new_keys:
            if key not in self.api_keys:
                self.api_keys.append(key)
                self.key_usage_counts[key] = 0

    def _get_current_key(self):
        if not self.api_keys:
            return None

        start_index = self.current_key_index
        # Find a key that hasn't exceeded its usage limit
        while True:
            key = self.api_keys[self.current_key_index]
            if self.key_usage_counts[key] < self.MAX_CALLS_PER_KEY:
                return key

            self._rotate_key()
            if self.current_key_index == start_index:
                logging.critical("All API keys have exceeded their usage limits!")
                return None

    def _rotate_key(self):
        if self.api_keys:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logging.info(f"Rotated API key to index {self.current_key_index}")

    def generate_text(self, prompt, retries=3, require_json=False):

        system_prompt = (
            "Kamu adalah Nexus-AGI, agen otonom yang bertujuan menghasilkan pendapatan melalui pekerjaan freelance dan affiliate TikTok. "
            "Gunakan Thinking Mode untuk menganalisis setiap tugas secara mendalam sebelum mengambil tindakan. "
            "Prioritaskan pekerjaan yang dapat kamu selesaikan 100% otonom tanpa campur tangan manusia. "
            "Jika sebuah tugas memerlukan input manusia (misalnya, verifikasi identitas, persetujuan akhir yang sensitif, penyelesaian CAPTCHA), "
            "tandai tugas tersebut sebagai BLOCKED dan cari tugas lain yang sepenuhnya otonom. "
            "Untuk pekerjaan freelance, fokus pada tugas Coding, Menulis, atau Analisis Data. "
            "Untuk TikTok affiliate, fokus pada produk yang memiliki aset visual yang jelas dan dapat diolah oleh Veo 3. "
            "Selalu pertimbangkan efisiensi sumber daya dan hindari aktivitas yang dapat menyebabkan deteksi bot yang agresif.\n\n"
            f"TUGAS SAAT INI:\n{prompt}"
        )

        for _ in range(retries):
            api_key = self._get_current_key()
            if not api_key:
                 logging.error("API Key not found, cannot generate text")
                 return "Error: No API Key available."

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={api_key}"

            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {}
            }

            if require_json:
                data["generationConfig"]["responseMimeType"] = "application/json"

            try:
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)

                if response.status_code == 200:
                    self.key_usage_counts[api_key] += 1
                    result = response.json()
                    # Parse the response structure (adjust if standard Google AI Studio structure varies for gemma)
                    try:
                        text = result['candidates'][0]['content']['parts'][0]['text']
                        return text
                    except (KeyError, IndexError) as e:
                        logging.error(f"Failed to parse LLM response: {result}. Error: {e}")
                        return "Error parsing response."
                elif response.status_code in [429, 403]: # Rate limit or forbidden
                    logging.warning(f"API Key {self.current_key_index} rate limited or forbidden (status {response.status_code}). Rotating...")
                    self._rotate_key()
                else:
                    logging.error(f"API request failed with status code {response.status_code}: {response.text}")
                    return f"API Error: {response.status_code}"

            except requests.exceptions.RequestException as e:
                 logging.error(f"Request exception during LLM call: {e}")

        return "Error: Max retries exceeded for LLM generation."
