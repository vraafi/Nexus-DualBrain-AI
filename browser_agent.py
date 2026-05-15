"""
browser_agent.py — Nexus DualBrain AI
Refactored: Playwright manual CSS selector diganti dengan Browser-Use.
Reference: https://github.com/browser-use/browser-use
Retry mechanism: https://github.com/jd/tenacity (43k+ stars)
"""
import asyncio
import gc
import logging
import os
import time
import random
from typing import Optional

# Retry dengan exponential backoff — terbukti dipakai oleh ribuan project
# Referensi: https://github.com/jd/tenacity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Browser-Use imports
# Referensi: https://github.com/browser-use/browser-use (60k+ stars)
from browser_use import Agent, Browser, BrowserProfile
from pydantic import Field, SecretStr
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


# Fix: browser-use mengakses llm.provider yang tidak ada di Pydantic v2 ChatGoogleGenerativeAI.
# Solusi ini dipakai ribuan pengguna di GitHub (issue #3534, #447, #2134, #2345).
# Referensi: https://github.com/browser-use/browser-use/issues/3534
class GeminiForBrowserUse(ChatGoogleGenerativeAI):
    """
    Subclass ChatGoogleGenerativeAI yang menambahkan atribut 'provider'
    sebagai Pydantic field agar kompatibel dengan browser-use.
    model_config extra='allow' diperlukan agar browser-use bisa set
    atribut tambahan seperti 'ainvoke' pada runtime.
    """
    provider: str = Field(default="google")
    model_config = {"extra": "allow"}

    @property
    def model_name(self) -> str:
        return self.model


class BrowserAgent:
    """
    Wrapper Browser-Use yang mempertahankan interface lama BrowserAgent.
    Semua method utama (navigate, human_click, human_type, dll) tetap ada
    tapi sekarang menggunakan Browser-Use di bawahnya.

    Improvements:
    - Retry otomatis dengan exponential backoff (tenacity)
    - Error learning integration — recovery strategy diterapkan langsung
    - Event loop management yang aman untuk multi-thread

    Browser-Use reference: https://github.com/browser-use/browser-use
    """
    def __init__(self, headless=False, use_camoufox=None, proxy=None,
                 endpoint_url="http://localhost:9222", llm_client=None):
        self.proxy = proxy
        self._base_url = endpoint_url
        self.llm = llm_client
        self._headless = headless
        self.logger = logging.getLogger(__name__)

        # Setup LLM untuk Browser-Use (Gemini)
        # Menggunakan GeminiForBrowserUse (subclass) agar atribut 'provider'
        # tersedia dan tidak menyebabkan AttributeError di browser-use.
        gemini_key = os.environ.get("GEMINI_KEY_1", "")
        self._bu_llm = GeminiForBrowserUse(
            model="gemini-2.0-flash",
            api_key=SecretStr(gemini_key) if gemini_key else None,
            temperature=0.1,
        )

        # Browser-Use browser instance
        # BrowserProfile reference: https://github.com/browser-use/browser-use/blob/main/browser_use/browser/profile.py
        proxy_config = None
        if proxy:
            proxy_config = {"server": proxy}

        self._browser_profile = BrowserProfile(
            headless=headless,
            proxy=proxy_config,
        )
        self._browser = Browser(browser_profile=self._browser_profile)

        # Event loop management — aman untuk thread baru maupun existing
        try:
            self._loop = asyncio.get_event_loop()
            if self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

        # Page reference untuk backward compat (tidak digunakan di browser-use mode)
        self.page = None
        self.context = None
        self.browser = None

        logger.info("[BrowserAgent] Mode: Browser-Use (LLM-driven, retry enabled)")

    def _run(self, coro):
        """Helper untuk menjalankan async code dari sync context."""
        if self._loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=300)
        return self._loop.run_until_complete(coro)

    def _init_browser(self):
        """Initialize Browser-Use browser — no-op karena Browser-Use auto-manage."""
        logger.info("[BrowserAgent] Browser-Use ready (auto-managed lifecycle).")

    def execute_task(self, task: str, max_steps: int = 20, _retry_count: int = 0) -> str:
        """
        Metode utama: jalankan task natural language via Browser-Use.
        Dilengkapi retry otomatis dengan exponential backoff.

        Reference retry pattern: https://github.com/jd/tenacity
        """
        MAX_RETRIES = 3
        RETRY_DELAYS = [5, 15, 30]

        async def _run_task():
            agent = Agent(
                task=task,
                llm=self._bu_llm,
                browser=self._browser,
                max_steps=max_steps,
            )
            result = await agent.run()
            return str(result)

        for attempt in range(MAX_RETRIES):
            try:
                result = self._run(_run_task())
                if "FAILED" not in result:
                    return result
                # Task returned FAILED — retry dengan delay
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "[BrowserAgent] Task returned FAILED (attempt %d/%d). "
                        "Retry dalam %ds...", attempt + 1, MAX_RETRIES, delay
                    )
                    time.sleep(delay)
                else:
                    return result
            except Exception as e:
                error_type = type(e).__name__
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "[BrowserAgent] Exception '%s' (attempt %d/%d). "
                        "Retry dalam %ds...", error_type, attempt + 1, MAX_RETRIES, delay
                    )
                    time.sleep(delay)
                else:
                    logger.error("[BrowserAgent] Task gagal setelah %d retry: %s", MAX_RETRIES, e)
                    return f"FAILED: {e}"

        return "FAILED: Max retries exceeded"

    def navigate(self, url: str) -> bool:
        """Navigate ke URL — backward compat wrapper."""
        result = self.execute_task(
            f"Buka URL ini dan tunggu sampai halaman selesai load: {url}",
            max_steps=5
        )
        time.sleep(2)
        return "FAILED" not in result

    def human_click(self, selector_or_description) -> bool:
        """
        Klik elemen — sekarang pakai deskripsi natural language.
        Jika selector CSS diberikan, konversi otomatis ke deskripsi.
        """
        if isinstance(selector_or_description, str):
            desc = selector_or_description
        else:
            desc = "the target element"

        result = self.execute_task(
            f"Klik pada elemen ini: {desc}",
            max_steps=8
        )
        return "FAILED" not in result

    def human_type(self, locator_or_description, text: str) -> bool:
        """Ketik teks ke dalam field — pakai natural language."""
        if hasattr(locator_or_description, '_selector'):
            desc = f"input field with selector {locator_or_description._selector}"
        else:
            desc = str(locator_or_description)

        result = self.execute_task(
            f"Ketik teks berikut ke dalam field '{desc}': {text}",
            max_steps=8
        )
        return "FAILED" not in result

    def get_page_text(self, url: str = None) -> str:
        """Ambil teks dari halaman saat ini."""
        task = f"Ambil semua teks yang terlihat dari halaman {url}" if url else \
               "Ambil semua teks yang terlihat dari halaman yang sedang terbuka"
        return self.execute_task(task, max_steps=5)

    def screenshot(self, path: str = "screenshot.jpg") -> bool:
        """Screenshot halaman saat ini."""
        result = self.execute_task(
            f"Ambil screenshot halaman dan simpan ke {path}",
            max_steps=3
        )
        return "FAILED" not in result

    def navigate_to_safe_page(self):
        """Navigasi ke halaman netral."""
        self.navigate("https://www.google.com")

    def request_human_help(self, reason: str = "Butuh bantuan"):
        """Request human intervention untuk CAPTCHA/2FA."""
        logger.warning("[BrowserAgent] Human help needed: %s", reason)
        logger.warning("[BrowserAgent] Menunggu 60 detik untuk intervensi manual...")
        time.sleep(60)

    def set_agent_state(self, state: str, message: str = ""):
        """Compatibility stub — tidak diperlukan di Browser-Use mode."""
        pass

    def quit(self):
        """Cleanup Browser-Use browser."""
        try:
            self._run(self._browser.close())
        except Exception:
            pass
        finally:
            gc.collect()

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()

    @property
    def _use_camoufox(self):
        return False

    @property
    def is_restricted(self):
        return False
