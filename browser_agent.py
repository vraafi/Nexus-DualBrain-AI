import logging
import gc
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

class BrowserAgent:
    def __init__(self):
        self.driver = None
        logging.basicConfig(level=logging.INFO)
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]

    def random_delay(self, min_sec=2.0, max_sec=5.0):
        """Simulates human-like delay."""
        time.sleep(random.uniform(min_sec, max_sec))

    def _init_driver(self):
        """Initializes the browser driver with low-memory optimizations and stealth options."""
        options = Options()
        # Optimizations for low-spec hardware
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--single-process')

        # Anti-detection stealth features
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Rotate user agent
        selected_ua = random.choice(self.user_agents)
        options.add_argument(f'user-agent={selected_ua}')

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            logging.info("Browser driver initialized.")
        except WebDriverException as e:
            logging.error(f"Failed to initialize browser: {e}")
            self.quit()
            raise

    def get(self, url):
        """Navigates to a URL with strict error handling and memory management."""
        if not self.driver:
            self._init_driver()

        try:
            logging.info(f"Navigating to {url}")
            self.driver.get(url)
            # Ensure only one heavy tab is open by closing others if any leaked
            while len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])

        except TimeoutException:
            logging.error(f"Timeout while loading {url}. Quitting driver to free memory.")
            self.quit()
            return False
        except Exception as e:
            logging.error(f"Error navigating to {url}: {e}. Quitting driver.")
            self.quit()
            return False
        return True

    def find_element(self, by, value, timeout=10):
        if not self.driver:
            return None
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            logging.error(f"Element {value} not found within {timeout}s.")
            return None
        except Exception as e:
            logging.error(f"Error finding element {value}: {e}")
            return None

    def quit(self):
        """Explicitly closes the browser and forces garbage collection."""
        if self.driver:
            try:
                self.driver.quit()
                logging.info("Browser driver quit successfully.")
            except Exception as e:
                logging.error(f"Error while quitting driver: {e}")
            finally:
                self.driver = None
                # Strict Exit Criteria: explicitly clear RAM
                del self.driver
                self.driver = None
                gc.collect()
                logging.info("Garbage collection triggered to clear RAM.")
