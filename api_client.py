"""
api_client.py — Client untuk Gemini/Gemma API dengan multi-key rotation & exponential backoff
Update: Support model hierarki 3-tier (31b → 26b → flash-lite) + NEGOTIATION_MODEL
Fix: Google Search 500 error → DuckDuckGo sebagai primary search, Gemini tanpa tool sebagai fallback
"""

import requests
import json
import logging
import os
import time
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

    def _search_duckduckgo(self, query):
        """
        Web search menggunakan DuckDuckGo — tidak butuh API key, tidak ada 500 error.
        Primary search method.
        """
        logging.info(f"DuckDuckGo Search: '{query}'")
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if results:
                snippets = [
                    f"[{r.get('title', '')}]\n{r.get('body', '')}"
                    for r in results if r.get("body")
                ]
                return "\n\n".join(snippets[:5])
            return "Tidak ada hasil ditemukan."
        except ImportError:
            logging.warning("ddgs/duckduckgo_search tidak terinstall. Jalankan: pip install ddgs")
            return ""
        except Exception as e:
            logging.warning(f"DuckDuckGo search gagal: {e}")
            return ""

    def _search_web_safe(self, query):
        """
        Fallback search via Gemini tanpa google_search tool.
        Menghindari 500 Internal Server Error dari Gemini google_search tool.
        """
        logging.info(f"Gemini Safe Search (no tool): '{query}'")
        try:
            prompt = (
                f"Berikan penjelasan dan solusi untuk query berikut berdasarkan pengetahuanmu:\n"
                f"'{query}'\n\n"
                "Fokus pada informasi yang relevan untuk debugging dan perbaikan kode Python."
            )
            # Panggil tanpa use_google_search=True untuk menghindari 500 error
            result = self._make_api_call(prompt, use_google_search=False)
            return result if result else "Tidak ada hasil."
        except Exception as e:
            logging.error(f"Gemini safe search gagal: {e}")
            return "Tidak ada hasil search."

    def _search_web(self, query):
        """
        Web search dengan strategi bertingkat:
        1. DuckDuckGo (primary — bebas API key, tidak ada 500 error)
        2. Gemini tanpa google_search tool (fallback — hindari 500 error)
        3. Return kosong jika semua gagal
        """
        logging.info(f"Web Search: '{query}'")

        # Primary: DuckDuckGo
        result = self._search_duckduckgo(query)
        if result:
            return result

        # Fallback: Gemini tanpa tool
        logging.info("DuckDuckGo tidak ada hasil. Fallback ke Gemini safe search...")
        result = self._search_web_safe(query)
        if result:
            return result

        return "Pencarian tidak membuahkan hasil."

    def generate_content(self, prompt, context="", require_json=False,
                         allow_search=False, use_codegen_model=False,
                         use_negotiation_model=False, image_base64=None):
        """
        Generate konten dari LLM.
        - use_codegen_model=True      → pakai gemma-4-31b-it (terkuat, untuk code)
        - use_negotiation_model=True  → pakai gemma-4-26b-a4b-it (menengah, untuk negosiasi)
        - default                     → gemini-3.1-flash-lite-preview (hemat, high-frequency)
        - allow_search=True           → LLM bisa request web search otomatis (via DuckDuckGo)
        - image_base64                → Kirim gambar ke Gemini (Vision)
        """
        original_model = self.model_name

        # Pilih model berdasarkan prioritas
        if use_codegen_model and self.model_name != CODEGEN_MODEL:
            self._switch_model(CODEGEN_MODEL)
        elif use_negotiation_model and self.model_name != NEGOTIATION_MODEL:
            self._switch_model(NEGOTIATION_MODEL)

        # Web search jika diizinkan (jangan lakukan jika ada gambar untuk hemat biaya)
        if allow_search and not image_base64:
            search_prompt = (
                f"Task:\n{prompt}\n\n"
                "Apakah kamu perlu mencari dokumentasi web terbaru untuk menyelesaikan ini? "
                "Jika YA, balas HANYA dengan query pencarian singkat (maks 100 karakter). "
                "Jika TIDAK, balas dengan tepat 'NO_SEARCH'."
            )
            search_decision = self._make_api_call(search_prompt, require_json=False, use_thinking=False)

            if search_decision and "NO_SEARCH" not in search_decision and len(search_decision.strip()) < 150:
                web_context = self._search_web(search_decision.strip())
                context = f"{context}\n\nWeb Search Results:\n{web_context}"

        full_prompt = f"Context: {context}\n\nPrompt: {prompt}" if context else prompt
        result = self._make_api_call(full_prompt, require_json, image_base64=image_base64)

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
                result = self._make_api_call(full_prompt, require_json, image_base64=image_base64)
                if result:
                    break

        # Restore model asal
        if self.model_name != original_model:
            self._switch_model(original_model)

        return result

    def _make_api_call(self, full_prompt, require_json=False, use_thinking=True,
                       image_base64=None, use_google_search=False):
        """
        HTTP call ke Gemini/Gemma API dengan exponential backoff dan key rotation.
        CATATAN: use_google_search=True menyebabkan 500 error pada model Gemma.
        Gunakan _search_web() atau _search_duckduckgo() sebagai gantinya.
        """
        max_retries = self.model_config["max_retries"]

        for attempt in range(max_retries):
            key = self._get_current_key()
            url = f"{self.base_url}?key={key}"
            headers = {"Content-Type": "application/json"}

            parts = [{"text": full_prompt}]
            if image_base64:
                parts.insert(0, {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                })

            data = {"contents": [{"role": "user", "parts": parts}]}

            # PENTING: google_search tool hanya didukung model Gemini Flash/Pro tertentu.
            # Pada model Gemma (31b, 26b) ini menyebabkan 500 Internal Server Error.
            # Nonaktifkan secara default — gunakan DuckDuckGo sebagai gantinya.
            supports_google_search = self.model_config.get("supports_google_search", False)
            if use_google_search and supports_google_search:
                data["tools"] = [{"google_search": {}}]
            elif use_google_search and not supports_google_search:
                logging.warning(
                    f"Model {self.model_name} tidak mendukung google_search tool. "
                    "Melewati tool injection untuk menghindari 500 error."
                )

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
                        resp_parts = candidates[0].get("content", {}).get("parts", [])
                        if resp_parts:
                            return resp_parts[0].get("text", "")
                    logging.warning("Respons kosong dari API.")
                    return None

                elif response.status_code == 429:
                    delay = min(self.model_config["rate_limit_delay"] * (2 ** attempt), 300)
                    logging.warning(f"Rate limit. Menunggu {delay}s lalu rotasi key...")
                    time.sleep(delay)
                    self._rotate_key()

                elif response.status_code in (500, 502, 503, 504):
                    delay = min(5 * (2 ** attempt), 120)
                    logging.warning(
                        f"Server error {response.status_code}: {response.text[:300]}. "
                        f"Retry dalam {delay}s..."
                    )
                    # Jika 500 dan ada google_search tool aktif, nonaktifkan dan coba lagi
                    if response.status_code == 500 and "tools" in data:
                        logging.warning(
                            "Kemungkinan 500 disebabkan google_search tool. "
                            "Menonaktifkan tool dan retry tanpa delay..."
                        )
                        data.pop("tools", None)
                        continue
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
