import gc
import logging
import time
import random
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from python_ghost_cursor.playwright_sync import create_cursor

class BrowserAgent:
    def __init__(self, headless=True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def _init_browser(self):
        try:
            self.playwright = sync_playwright().start()

            # Implement Persistent Context for session management (Logins/Cookies)
            user_data_dir = "./browser_profile"

            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=self.headless,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--single-process",
                    "--disable-blink-features=AutomationControlled"
                ],
                no_viewport=True
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

            # Apply strict anti-bot measures: Match hardware to 8GB RAM specs to avoid fingerprint anomalies
            init_scripts = """
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 4
                });
            """
            self.page.add_init_script(init_scripts)

            # Apply stealth to evade bot detection
            stealth_sync(self.page)

            # Initialize Ghost Cursor
            self.cursor = create_cursor(self.page)

            self.page.set_default_timeout(60000)
            logging.info(f"Playwright browser initialized (headless={self.headless}, persistent_profile, strict_stealth, ghost_cursor).")
        except Exception as e:
            logging.error(f"Failed to init browser: {e}")
            self.quit()

    def _human_delay(self, min_ms=1000, max_ms=3000):
        delay = random.uniform(min_ms, max_ms)
        time.sleep(delay / 1000.0)

    def human_type(self, locator, text):
        """Types text character by character with human-like delays."""
        locator.click()
        for char in text:
            self.page.keyboard.type(char)
            delay = random.uniform(50, 150) / 1000.0
            time.sleep(delay)

    def human_click(self, selector):
        """Uses Ghost Cursor to simulate human mouse movement before clicking."""
        try:
            if hasattr(self, 'cursor'):
                self.cursor.click(selector)
            else:
                self.page.click(selector)
        except Exception as e:
            logging.warning(f"Ghost cursor failed on {selector}, falling back to standard click. Error: {e}")
            self.page.click(selector)

    def navigate(self, url):
        if not self.page:
            self._init_browser()
        try:
            self._human_delay()
            self.page.goto(url)
            self.page.wait_for_load_state("networkidle")
            self._human_delay(2000, 4000)
            return True
        except Exception as e:
            logging.error(f"Failed to navigate to {url}: {e}")
            return False

    def quit(self):
        try:
            if self.context:
                self.context.close()
        except Exception as e:
            logging.error(f"Error closing Playwright context: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            gc.collect()
            logging.info("Browser closed and memory explicitly cleared.")

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
