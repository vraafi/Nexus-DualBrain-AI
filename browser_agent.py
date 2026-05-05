import gc
import logging
import time
import random
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

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

            # Apply stealth to evade bot detection
            stealth_sync(self.page)

            self.page.set_default_timeout(60000)
            logging.info(f"Playwright browser initialized (headless={self.headless}, persistent_profile, stealth_enabled).")
        except Exception as e:
            logging.error(f"Failed to init browser: {e}")
            self.quit()

    def _human_delay(self, min_ms=1000, max_ms=3000):
        delay = random.uniform(min_ms, max_ms)
        time.sleep(delay / 1000.0)

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
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logging.error(f"Error closing Playwright: {e}")
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
