import requests
import json
import logging
import os

class GeminiClient:
    def __init__(self, api_keys):
        self.api_keys = api_keys
        self.current_key_idx = 0
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent"

    def _get_current_key(self):
        return self.api_keys[self.current_key_idx]

    def _rotate_key(self):
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        logging.info(f"Rotated API key. Now using key index {self.current_key_idx}")

    def generate_content(self, prompt, context="", require_json=False):
        full_prompt = f"Context: {context}\n\nPrompt: {prompt}"

        for _ in range(len(self.api_keys)): # Try all keys before failing
            key = self._get_current_key()
            url = f"{self.base_url}?key={key}"
            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "thinkingConfig": {"thinkingLevel": "high"}
                }
            }

            if require_json:
                data["generationConfig"]["responseMimeType"] = "application/json"

            try:
                response = requests.post(url, headers=headers, data=json.dumps(data))
                if response.status_code == 200:
                    text_response = response.json()['candidates'][0]['content']['parts'][0]['text']

                    # Log the thinking process if available, but return the final structured answer
                    # Assuming Gemma with thinkingConfig might return tags or separated content,
                    # but typically the 'text' field contains the final structured output when responseMimeType is json.
                    return text_response
                elif response.status_code == 429: # Rate limit exceeded
                    logging.warning("Rate limit exceeded for current key. Rotating...")
                    self._rotate_key()
                else:
                    logging.error(f"API Error {response.status_code}: {response.text}")
                    return None
            except Exception as e:
                 logging.error(f"Request failed: {e}")
                 self._rotate_key()

        logging.error("All API keys failed or rate-limited.")
        return None
