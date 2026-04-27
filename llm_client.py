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

    def _get_current_key(self):
        if not self.api_keys:
            return None
        return self.api_keys[self.current_key_index]

    def _rotate_key(self):
        if self.api_keys:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logging.info(f"Rotated API key to index {self.current_key_index}")

    def generate_text(self, prompt, retries=3, require_json=False):
        for _ in range(retries):
            api_key = self._get_current_key()
            if not api_key:
                 logging.error("API Key not found, cannot generate text")
                 return "Error: No API Key available."

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={api_key}"

            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {}
            }

            if require_json:
                data["generationConfig"]["responseMimeType"] = "application/json"

            try:
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)

                if response.status_code == 200:
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
