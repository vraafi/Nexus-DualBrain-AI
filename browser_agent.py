import gc
import logging
import time
import random
import os
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# Mencoba import Camoufox untuk stealth yang lebih baik
try:
    from camoufox.sync_api import Camoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    logging.warning("Camoufox tidak tersedia. Menggunakan Playwright standar.")

# Fallback aman jika python-ghost-cursor tidak bisa diinstall
try:
    from python_ghost_cursor.playwright_sync import create_cursor
    GHOST_CURSOR_AVAILABLE = True
except ImportError:
    GHOST_CURSOR_AVAILABLE = False
    logging.warning("python-ghost-cursor tidak tersedia. Fallback ke standard click.")

class BrowserAgent:
    def __init__(self, headless=True, use_camoufox=True):
        self.headless = headless
        self.use_camoufox = use_camoufox and CAMOUFOX_AVAILABLE
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.cursor = None

    def _init_browser(self):
        try:
            if self.use_camoufox:
                logging.info("Initializing browser with Camoufox...")
                self.browser = Camoufox(
                    headless=self.headless,
                    humanize=True,
                    # Proxy sangat disarankan untuk Camoufox, tapi kita biarkan opsional
                    # proxy=os.environ.get("RESIDENTIAL_PROXY") 
                )
                self.page = self.browser.new_page()
            else:
                self.playwright = sync_playwright().start()
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

                init_scripts = """
                    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
                """
                self.page.add_init_script(init_scripts)
                stealth_sync(self.page)

            # Inisialisasi ghost cursor dengan fallback
            if GHOST_CURSOR_AVAILABLE:
                try:
                    self.cursor = create_cursor(self.page)
                except Exception as e:
                    logging.warning(f"Ghost cursor gagal init: {e}. Pakai standard click.")
                    self.cursor = None
            else:
                self.cursor = None

            self.page.set_default_timeout(60000)
            logging.info(f"Browser initialized (Camoufox={self.use_camoufox}, headless={self.headless}, ghost_cursor={self.cursor is not None}).")
        except Exception as e:
            logging.error(f"Failed to init browser: {e}")
            self.quit()

    def _human_delay(self, min_ms=1000, max_ms=3000):
        delay = random.uniform(min_ms, max_ms)
        time.sleep(delay / 1000.0)

    def human_type(self, locator, text):
        try:
            locator.click()
            self._human_delay(500, 1000)
            locator.press_sequentially(text, delay=100)
        except Exception as e:
            logging.error(f"Failed during human_type: {e}")
            try:
                locator.fill(text)
            except Exception:
                pass

    def human_click(self, selector):
        try:
            if self.cursor is not None:
                self.cursor.click(selector)
            else:
                self.page.click(selector)
        except Exception as e:
            logging.warning(f"Click gagal pada {selector}, fallback standard click. Error: {e}")
            try:
                self.page.click(selector)
            except Exception as e2:
                logging.error(f"Standard click juga gagal: {e2}")

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
            if self.use_camoufox and self.browser:
                self.browser.close()
            elif self.context:
                self.context.close()
        except Exception as e:
            logging.error(f"Error closing browser/context: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            self.cursor = None
            gc.collect()
            logging.info("Browser closed and memory cleared.")

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
