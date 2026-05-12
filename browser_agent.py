import gc
import logging
import time
import random
import os
import subprocess
from playwright.sync_api import sync_playwright

try:
    from python_ghost_cursor.playwright_sync import create_cursor
    GHOST_CURSOR_AVAILABLE = True
except ImportError:
    GHOST_CURSOR_AVAILABLE = False
    logging.warning("python-ghost-cursor tidak tersedia. Fallback ke standard click.")


def _get_cdp_candidates(base_url: str) -> list:
    """
    Bangun daftar URL CDP untuk dicoba secara berurutan.
    1. BRAVE_CDP_URL dari env (jika di-set, langsung pakai ini saja)
    2. localhost (WSL2 mirrored networking — Windows 11 default)
    3. IP default gateway dari /proc/net/route
    4. IP default gateway dari `ip route`
    5. Nameserver dari resolv.conf (bukan 10.255.255.254)
    """
    port = base_url.split(":")[-1].strip("/")

    override = os.environ.get("BRAVE_CDP_URL", "").strip()
    if override:
        logging.info(f"BRAVE_CDP_URL dari env: {override}")
        return [override]

    candidates = []

    # 1. localhost — paling sederhana, bekerja di WSL2 mirrored networking
    candidates.append(f"http://localhost:{port}")

    # 2. Default gateway dari /proc/net/route
    try:
        with open("/proc/net/route") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == "00000000" and parts[2] != "00000000":
                    gw_bytes = bytes.fromhex(parts[2])
                    gw_ip = ".".join(str(b) for b in reversed(gw_bytes))
                    url = f"http://{gw_ip}:{port}"
                    if url not in candidates:
                        candidates.append(url)
                    break
    except Exception:
        pass

    # 3. Default gateway dari `ip route`
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if "default via" in line:
                gw_ip = line.split("via")[1].strip().split()[0]
                url = f"http://{gw_ip}:{port}"
                if url not in candidates:
                    candidates.append(url)
                break
    except Exception:
        pass

    # 4. Nameserver dari resolv.conf (skip DNS WSL2 mirrored)
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.startswith("nameserver"):
                    ns = line.strip().split()[1]
                    if ns not in ("10.255.255.254", "127.0.0.1", "::1"):
                        url = f"http://{ns}:{port}"
                        if url not in candidates:
                            candidates.append(url)
    except Exception:
        pass

    return candidates


class BrowserAgent:
    """
    Agent browser yang HANYA terhubung ke Brave via CDP (Remote Debugging).

    Sebelum menjalankan agent, buka Brave di Windows dengan:
        cmd /c start brave --remote-debugging-port=9222

    Kode akan otomatis mencoba beberapa endpoint (localhost, gateway IP, dll).
    Jika tetap gagal, set manual di .env:
        BRAVE_CDP_URL=http://localhost:9222
    """

    def __init__(self, headless=False, use_camoufox=False, proxy=None,
                 endpoint_url="http://localhost:9222"):
        self.proxy = proxy
        self._base_url = endpoint_url
        self.endpoint_url = None

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.cursor = None

    def _try_connect(self, url: str) -> bool:
        """Coba konek ke satu URL CDP. Return True jika berhasil."""
        try:
            logging.info(f"Mencoba konek ke Brave: {url} ...")
            pw = sync_playwright().start()
            browser = pw.chromium.connect_over_cdp(url, timeout=8000)
            if not browser.contexts:
                pw.stop()
                logging.warning(f"{url} terhubung tapi tidak ada tab aktif.")
                return False
            self.playwright = pw
            self.browser = browser
            self.endpoint_url = url
            return True
        except Exception as e:
            logging.warning(f"Gagal konek ke {url}: {e}")
            try:
                pw.stop()
            except Exception:
                pass
            return False

    def _init_browser(self):
        candidates = _get_cdp_candidates(self._base_url)
        logging.info(f"Urutan endpoint yang akan dicoba: {candidates}")
        logging.info("Pastikan Brave sudah berjalan dengan:")
        logging.info("  cmd /c start brave --remote-debugging-port=9222")

        connected = False
        for url in candidates:
            if self._try_connect(url):
                connected = True
                break

        if not connected:
            raise RuntimeError(
                f"Gagal konek ke Brave di semua endpoint yang dicoba: {candidates}\n\n"
                f"Solusi:\n"
                f"  1. Tutup semua proses Brave yang sedang berjalan (Task Manager).\n"
                f"  2. Buka CMD Windows dan jalankan:\n"
                f"       cmd /c start brave --remote-debugging-port=9222\n"
                f"  3. Tunggu Brave terbuka sempurna (ada minimal 1 tab).\n"
                f"  4. Jalankan agent lagi.\n\n"
                f"  Jika tetap gagal, tambahkan di file .env:\n"
                f"       BRAVE_CDP_URL=http://localhost:9222\n\n"
                f"  Atau izinkan port 9222 di Windows Firewall:\n"
                f"    (PowerShell Admin) netsh advfirewall firewall add rule name=\"Brave CDP\" "
                f"dir=in action=allow protocol=TCP localport=9222"
            )

        self.context = self.browser.contexts[0]
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(60000)

        if GHOST_CURSOR_AVAILABLE:
            try:
                self.cursor = create_cursor(self.page)
            except Exception as e:
                logging.warning(f"Ghost cursor gagal init: {e}. Pakai standard click.")
                self.cursor = None
        else:
            self.cursor = None

        logging.info(f"Berhasil terhubung ke Brave via {self.endpoint_url}. Tab aktif: {self.page.url}")

    def _cleanup_playwright(self):
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        finally:
            self.playwright = None
            self.browser = None
            self.context = None
            self.page = None
            self.cursor = None

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
        """
        Klik elemen. Menerima string CSS selector ATAU Playwright Locator object.
        Jika Locator: klik langsung via bounding box (kompatibel dengan ghost cursor).
        Jika string: pakai cursor.click() atau page.click().
        """
        from playwright.sync_api import Locator
        is_locator = isinstance(selector, Locator)
        try:
            if is_locator:
                # Locator object — ghost cursor pakai koordinat bounding box
                selector.scroll_into_view_if_needed()
                if self.cursor is not None:
                    box = selector.bounding_box()
                    if box:
                        cx = box["x"] + box["width"] / 2
                        cy = box["y"] + box["height"] / 2
                        self.page.mouse.click(cx, cy)
                    else:
                        selector.click()
                else:
                    selector.click()
            else:
                # String selector
                if self.cursor is not None:
                    self.cursor.click(selector)
                else:
                    self.page.click(selector)
        except Exception as e:
            logging.warning(f"Click gagal pada {selector}, fallback standard click. Error: {e}")
            try:
                if is_locator:
                    selector.click()
                else:
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
            if self.page:
                self.page.close()
        except Exception as e:
            logging.error(f"Error closing page: {e}")
        finally:
            self._cleanup_playwright()
            gc.collect()
            logging.info("Koneksi CDP ke Brave ditutup dan memori dibersihkan.")

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
