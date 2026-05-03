import gc
import logging
import time
from playwright.sync_api import sync_playwright

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
            # Hybrid Browser Mode: Can toggle headless=False for manual intervention
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--single-process"
                ]
            )
            # Ensure single tab logic
            self.context = self.browser.new_context()
            self.page = self.context.new_page()
            self.page.set_default_timeout(30000)
            logging.info(f"Playwright browser initialized (headless={self.headless}).")
        except Exception as e:
            logging.error(f"Failed to init browser: {e}")
            self.quit()

    def navigate(self, url):
        if not self.page:
            self._init_browser()
        try:
            self.page.goto(url)
            self.page.wait_for_load_state("networkidle")
            return True
        except Exception as e:
            logging.error(f"Failed to navigate to {url}: {e}")
            return False

    def quit(self):
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logging.error(f"Error closing Playwright: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            # Strict explicit RAM clearing
            del self.page
            del self.context
            del self.browser
            gc.collect()
            logging.info("Browser closed and memory explicitly cleared.")

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
