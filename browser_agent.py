import logging
import gc
import time
import random
import asyncio
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_sync

class BrowserAgent:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        logging.basicConfig(level=logging.INFO)
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]

    def random_delay(self, min_sec=1.0, max_sec=3.0):
        """Simulates human-like delay."""
        time.sleep(random.uniform(min_sec, max_sec))

    def _init_driver(self):
        """Initializes a persistent Playwright browser context with low-memory and stealth optimizations."""
        try:
            self.playwright = sync_playwright().start()

            # Optimizations for low-spec hardware
            args = [
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-gpu',
                '--disable-extensions',
                '--single-process',
                '--disable-blink-features=AutomationControlled'
            ]

            selected_ua = random.choice(self.user_agents)

            import os

            # Load stored state if available to bypass logins, preserving 100% autonomy
            state_file = os.path.join(os.getcwd(), "browser_state.json")
            storage_state = state_file if os.path.exists(state_file) else None

            # Use standard context for lighter memory footprint instead of heavy persistent context
            # Explicitly run headless=False so the user can interact visually when prompted for manual login
            self.browser = self.playwright.chromium.launch(headless=False, args=args)
            self.context = self.browser.new_context(
                user_agent=selected_ua,
                storage_state=storage_state
            )
            self.page = self.context.new_page()

            # Apply playwright-stealth to aggressively avoid bot detection
            stealth_sync(self.page)

            # Track state file to save upon exit
            self.state_file = state_file

            logging.info("Playwright headless stealth browser context initialized with storage_state for autonomy.")
        except Exception as e:
            logging.error(f"Failed to initialize persistent Playwright browser: {e}")
            self.quit()
            raise

    def get(self, url):
        """Navigates to a URL with strict error handling and memory management."""
        if not self.page:
            self._init_driver()

        try:
            logging.info(f"Navigating to {url}")
            # Ensure only one heavy tab is open by closing others
            pages = self.context.pages
            if len(pages) > 1:
                for p in pages[1:]:
                    p.close()

            self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
            return True

        except PlaywrightTimeoutError:
            logging.error(f"Timeout while loading {url}. Quitting driver to free memory.")
            self.quit()
            return False
        except Exception as e:
            logging.error(f"Error navigating to {url}: {e}. Quitting driver.")
            self.quit()
            return False

    def click(self, selector, timeout=10000):
        """Clicks an element with a timeout."""
        if not self.page:
            return False
        try:
            self.page.click(selector, timeout=timeout)
            return True
        except Exception as e:
            logging.error(f"Error clicking element {selector}: {e}")
            return False

    def fill(self, selector, text, timeout=10000):
        """Fills an input field."""
        if not self.page:
            return False
        try:
            self.page.fill(selector, text, timeout=timeout)
            return True
        except Exception as e:
            logging.error(f"Error filling element {selector}: {e}")
            return False

    def get_text(self, selector, timeout=10000):
        """Gets text content of an element."""
        if not self.page:
            return ""
        try:
            return self.page.text_content(selector, timeout=timeout)
        except Exception as e:
            logging.error(f"Error getting text from {selector}: {e}")
            return ""

    def pause_for_manual_login(self, platform_name):
        """Pauses the workflow and prompts the user to log in manually, as originally requested by the user."""
        logging.warning(f"Login wall detected for {platform_name}. Agent requires manual account setup.")
        input(f"Tolong masukkan detail akun login Anda di browser untuk {platform_name}. Tekan ENTER di terminal ini jika login sudah berhasil...")
        logging.info(f"Resuming automation for {platform_name} after manual user confirmation.")
        return True

    def quit(self):
        """Saves session state and explicitly closes the browser to force garbage collection."""
        try:
            if self.context:
                if hasattr(self, 'state_file'):
                    self.context.storage_state(path=self.state_file)
                    logging.info(f"Saved session state to {self.state_file}")
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logging.info("Playwright browser closed successfully.")
        except Exception as e:
            logging.error(f"Error while quitting driver: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None

            # Strict Exit Criteria: explicitly clear RAM
            gc.collect()
            logging.info("Garbage collection triggered to clear RAM.")
