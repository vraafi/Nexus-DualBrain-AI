"""
browser_agent.py — Nexus DualBrain AI
Refactored: Playwright manual CSS selector diganti dengan Browser-Use.
Reference: https://github.com/browser-use/browser-use
"""
import asyncio
import gc
import logging
import os
import time
import random
from typing import Optional

# Browser-Use imports
from browser_use import Agent, Browser, BrowserConfig
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

class BrowserAgent:
    """
    Wrapper Browser-Use yang mempertahankan interface lama BrowserAgent.
    Semua method utama (navigate, human_click, human_type, dll) tetap ada
    tapi sekarang menggunakan Browser-Use di bawahnya.

    Browser-Use reference: https://github.com/browser-use/browser-use
    """
    def __init__(self, headless=False, use_camoufox=None, proxy=None, endpoint_url="http://localhost:9222", llm_client=None):
        self.proxy = proxy
        self._base_url = endpoint_url
        self.llm = llm_client
        self._headless = headless
        self.logger = logging.getLogger(__name__)

        # Setup LLM untuk Browser-Use (Gemini)
        gemini_key = os.environ.get("GEMINI_KEY_1", "")
        self._bu_llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=gemini_key,
            temperature=0.1,
        )

        # Browser-Use browser instance
        self._browser_config = BrowserConfig(
            headless=headless,
            proxy={"server": proxy} if proxy else None,
        )
        self._browser = Browser(config=self._browser_config)

        # Loop untuk async operations
        self._loop = asyncio.new_event_loop()

        # Page reference untuk backward compat
        self.page = None
        self.context = None
        self.browser = None

        logger.info("[BrowserAgent] Mode: Browser-Use (LLM-driven, no CSS selectors)")

    def _run(self, coro):
        """Helper untuk menjalankan async code dari sync context."""
        return self._loop.run_until_complete(coro)

    def _init_browser(self):
        """Initialize Browser-Use browser."""
        logger.info("[BrowserAgent] Initializing Browser-Use...")
        # Browser-Use manages its own browser lifecycle
        pass

    def execute_task(self, task: str, max_steps: int = 20) -> str:
        """
        Metode utama: jalankan task natural language via Browser-Use.
        Ini menggantikan semua kombinasi navigate + click + type.

        Contoh:
        result = browser.execute_task(
            "Login ke Upwork dengan email user@mail.com dan password secret123"
        )
        """
        async def _run_task():
            agent = Agent(
                task=task,
                llm=self._bu_llm,
                browser=self._browser,
                max_steps=max_steps,
            )
            result = await agent.run()
            return str(result)

        try:
            return self._run(_run_task())
        except Exception as e:
            logger.error("[BrowserAgent] Task failed: %s", e)
            return f"FAILED: {e}"

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
            self._loop.close()
            gc.collect()

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()

    # Property untuk backward compat
    @property
    def _use_camoufox(self):
        return False

    @property
    def is_restricted(self):
        return False
