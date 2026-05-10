"""
api_client.py — Client untuk Gemini/Gemma API dengan multi-key rotation & exponential backoff
Update: Support model hierarki 3-tier (31b → 26b → flash-lite) + NEGOTIATION_MODEL
"""

import requests
import json
import logging
import os
import time
from duckduckgo_search import DDGS
from llm_config import LLM_MODELS, DEFAULT_LLM_MODEL, CODEGEN_MODEL, NEGOTIATION_MODEL, FALLBACK_MODEL


class GeminiClient:
    def __init__(self, api_keys):
        self.api_keys = api_keys
        self.current_key_idx = 0
        self.model_name = DEFAULT_LLM_MODEL
        self.model_config = LLM_MODELS[self.model_name]
        self.base_url = self.model_config["base_url"]

    def _get_current_key(self):
        return self.api_keys[self.current_key_idx]

    def _rotate_key(self):
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        logging.info(f"API key dirotasi. Sekarang menggunakan key index {self.current_key_idx}")

    def _switch_model(self, model_name: str):
        """Ganti model secara dinamis."""
        if model_name not in LLM_MODELS:
            logging.warning(f"Model '{model_name}' tidak dikenal. Tetap gunakan {self.model_name}.")
            return
        self.model_name = model_name
        self.model_config = LLM_MODELS[model_name]
        self.base_url = self.model_config["base_url"]
        logging.info(f"Model diganti ke: {model_name}")

    def _search_web(self, query):
        """Web search untuk memberikan konteks dokumentasi terkini ke LLM."""
        logging.info(f"Web search: '{query}'")
        try:
            results = DDGS().text(query, max_results=3)
            search_context = "\n".join([
                f"Source: {r.get('title')}\n{r.get('body')}"
                for r in results
            ])
            return search_context
        except Exception as e:
            logging.error(f"Search gagal: {e}")
            return "Tidak ada hasil search."

    def generate_content(self, prompt, context="", require_json=False,
                         allow_search=False, use_codegen_model=False,
                         use_negotiation_model=False):
        """
        Generate konten dari LLM.
        - use_codegen_model=True      → pakai gemma-4-31b-it (terkuat, untuk code)
        - use_negotiation_model=True  → pakai gemma-4-26b-a4b-it (menengah, untuk negosiasi)
        - default                     → gemini-3.1-flash-lite-preview (hemat, high-frequency)
        - allow_search=True           → LLM bisa request web search otomatis
        """
        original_model = self.model_name

        # Pilih model berdasarkan prioritas
        if use_codegen_model and self.model_name != CODEGEN_MODEL:
            self._switch_model(CODEGEN_MODEL)
        elif use_negotiation_model and self.model_name != NEGOTIATION_MODEL:
            self._switch_model(NEGOTIATION_MODEL)

        # Web search jika diizinkan
        if allow_search:
            search_prompt = (
                f"Task:\n{prompt}\n\n"
                "Apakah kamu perlu mencari dokumentasi web terbaru untuk menyelesaikan ini? "
                "Jika YA, balas HANYA dengan query pencarian. Jika TIDAK, balas dengan tepat 'NO_SEARCH'."
            )
            search_decision = self._make_api_call(search_prompt, require_json=False, use_thinking=False)

            if search_decision and "NO_SEARCH" not in search_decision and len(search_decision) < 150:
                web_context = self._search_web(search_decision.strip())
                context = f"{context}\n\nWeb Search Results:\n{web_context}"

        full_prompt = f"Context: {context}\n\nPrompt: {prompt}" if context else prompt
        result = self._make_api_call(full_prompt, require_json)

        # Kembalikan ke model asal
        if self.model_name != original_model:
            self._switch_model(original_model)

        # Fallback bertahap: 31b → 26b → flash-lite
        if result is None:
            fallback_chain = [NEGOTIATION_MODEL, FALLBACK_MODEL]
            for fallback in fallback_chain:
                if self.model_name == fallback:
                    continue
                logging.warning(f"Gagal di {self.model_name}. Fallback ke {fallback}.")
                self._switch_model(fallback)
                result = self._make_api_call(full_prompt, require_json)
                if result:
                    break

        # Restore model asal
        if self.model_name != original_model:
            self._switch_model(original_model)

        return result

    def _make_api_call(self, full_prompt, require_json=False, use_thinking=True):
        """HTTP call ke Gemini/Gemma API dengan exponential backoff dan key rotation."""
        max_retries = self.model_config["max_retries"]

        for attempt in range(max_retries):
            key = self._get_current_key()
            url = f"{self.base_url}?key={key}"
            headers = {"Content-Type": "application/json"}

            data = {"contents": [{"parts": [{"text": full_prompt}]}]}

            generation_config = {}
            supports_thinking = self.model_config.get("supports_thinking", False)
            if use_thinking and supports_thinking:
                generation_config["thinkingConfig"] = {"thinkingLevel": "high"}
            if require_json:
                generation_config["responseMimeType"] = "application/json"
            if generation_config:
                data["generationConfig"] = generation_config

            try:
                response = requests.post(
                    url, headers=headers,
                    data=json.dumps(data),
                    timeout=self.model_config["timeout"]
                )

                if response.status_code == 200:
                    candidates = response.json().get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                    logging.warning("Respons kosong dari API.")
                    return None

                elif response.status_code == 429:
                    delay = min(self.model_config["rate_limit_delay"] * (2 ** attempt), 300)
                    logging.warning(f"Rate limit. Menunggu {delay}s lalu rotasi key...")
                    time.sleep(delay)
                    self._rotate_key()

                elif response.status_code in (500, 502, 503, 504):
                    delay = min(5 * (2 ** attempt), 120)
                    logging.warning(f"Server error {response.status_code}. Retry dalam {delay}s...")
                    time.sleep(delay)

                elif response.status_code == 400:
                    logging.error(f"Bad Request 400: {response.text[:300]}")
                    return None

                else:
                    logging.error(f"API Error {response.status_code}: {response.text[:200]}")
                    return None

            except requests.exceptions.Timeout:
                delay = min(10 * (2 ** attempt), 120)
                logging.warning(f"Timeout pada attempt {attempt+1}. Retry dalam {delay}s...")
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                delay = min(5 * (2 ** attempt), 60)
                logging.error(f"Request gagal: {e}. Retry dalam {delay}s...")
                time.sleep(delay)
                self._rotate_key()

        logging.error("Semua percobaan API gagal.")
        return None
