import requests
import json
import logging
import os
from duckduckgo_search import DDGS

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

    def _search_web(self, query):
        """Performs a web search to provide up-to-date documentation context to the LLM."""
        logging.info(f"LLM requested web search for: '{query}'")
        try:
             results = DDGS().text(query, max_results=3)
             search_context = "\n".join([f"Source: {r.get('title')}\n{r.get('body')}" for r in results])
             return search_context
        except Exception as e:
             logging.error(f"Search failed: {e}")
             return "No search results available."

    def generate_content(self, prompt, context="", require_json=False, allow_search=False):
        # If search is allowed (e.g., for coding tasks), we first ask the LLM if it needs to search
        if allow_search:
            search_prompt = (
                f"You are given the following task:\n{prompt}\n\n"
                "Do you need to search the web for up-to-date API documentation or specific library syntax to solve this? "
                "If YES, reply with ONLY the search query. If NO, reply with exactly 'NO_SEARCH'."
            )
            # Make a quick, low-budget call to determine search needs
            search_decision = self._make_api_call(search_prompt, require_json=False, use_thinking=False)

            if search_decision and "NO_SEARCH" not in search_decision and len(search_decision) < 100:
                web_context = self._search_web(search_decision.strip())
                context = f"{context}\n\nWeb Search Results for '{search_decision.strip()}':\n{web_context}"

        full_prompt = f"Context: {context}\n\nPrompt: {prompt}"
        return self._make_api_call(full_prompt, require_json)

    def _make_api_call(self, full_prompt, require_json=False, use_thinking=True):
        for _ in range(len(self.api_keys)): # Try all keys before failing
            key = self._get_current_key()
            url = f"{self.base_url}?key={key}"
            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"parts": [{"text": full_prompt}]}]
            }

            generation_config = {}
            if use_thinking:
                generation_config["thinkingConfig"] = {"thinkingLevel": "high"}

            if require_json:
                generation_config["responseMimeType"] = "application/json"

            if generation_config:
                data["generationConfig"] = generation_config

            try:
                # Set a 60-second timeout for heavy LLM generations, especially on 'high' thinking budget
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=60)
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
