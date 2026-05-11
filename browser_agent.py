import gc
import logging
import time
import random
import os
from playwright.sync_api import sync_playwright

try:
    from python_ghost_cursor.playwright_sync import create_cursor
    GHOST_CURSOR_AVAILABLE = True
except ImportError:
    GHOST_CURSOR_AVAILABLE = False
    logging.warning("python-ghost-cursor tidak tersedia. Fallback ke standard click.")


def _get_wsl2_host_ip() -> str:
    """
    Cari IP host Windows dari WSL2 menggunakan beberapa metode:
    1. Default gateway dari /proc/net/route (paling reliable)
    2. Default gateway dari `ip route` command
    3. Nameserver dari /etc/resolv.conf (hanya jika bukan 10.255.255.254)
    Kembalikan None jika semua metode gagal.
    """
    # Metode 1: Baca default gateway dari /proc/net/route
    try:
        with open("/proc/net/route") as f:
            for line in f:
                parts = line.strip().split()
                # Kolom: Iface, Destination, Gateway, Flags, ...
                # Destination 00000000 = default route (0.0.0.0)
                if len(parts) >= 3 and parts[1] == "00000000" and parts[2] != "00000000":
                    # Gateway dalam format hex little-endian
                    gw_hex = parts[2]
                    gw_bytes = bytes.fromhex(gw_hex)
                    gw_ip = ".".join(str(b) for b in reversed(gw_bytes))
                    logging.info(f"Windows host IP (dari /proc/net/route): {gw_ip}")
                    return gw_ip
    except Exception as e:
        logging.warning(f"Gagal baca /proc/net/route: {e}")

    # Metode 2: Jalankan `ip route` untuk dapatkan default gateway
    try:
        import subprocess
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if "default via" in line:
                gw_ip = line.split("via")[1].strip().split()[0]
                logging.info(f"Windows host IP (dari ip route): {gw_ip}")
                return gw_ip
    except Exception as e:
        logging.warning(f"Gagal jalankan ip route: {e}")

    # Metode 3: Nameserver dari resolv.conf — abaikan 10.255.255.254 (DNS WSL2 mirrored)
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.startswith("nameserver"):
                    ns = line.strip().split()[1]
                    if ns not in ("10.255.255.254", "127.0.0.1", "::1"):
                        logging.info(f"Windows host IP (dari resolv.conf): {ns}")
                        return ns
    except Exception as e:
        logging.warning(f"Gagal baca /etc/resolv.conf: {e}")

    return None


def _resolve_brave_cdp_url(endpoint_url: str) -> str:
    """
    Resolusi URL CDP Brave.
    Priority:
    1. Env var BRAVE_CDP_URL (manual override)
    2. Deteksi otomatis IP Windows host di WSL2
    3. Fallback ke localhost (untuk WSL2 mirrored networking mode)
    """
    # 1. Manual override via .env
    override = os.environ.get("BRAVE_CDP_URL", "").strip()
    if override:
        logging.info(f"BRAVE_CDP_URL dari env: {override}")
        return override

    # 2. Hanya lakukan resolusi jika URL mengandung localhost/127.0.0.1
    if "localhost" in endpoint_url or "127.0.0.1" in endpoint_url:
        host_ip = _get_wsl2_host_ip()
        if host_ip:
            resolved = endpoint_url.replace("localhost", host_ip).replace("127.0.0.1", host_ip)
            logging.info(f"Endpoint CDP → {resolved}")
            return resolved
        else:
            # WSL2 mirrored networking: localhost langsung terhubung ke Windows
            logging.info("Tidak bisa deteksi IP Windows host. Menggunakan localhost langsung (mirrored networking).")

    return endpoint_url


class BrowserAgent:
    """
    Agent browser yang HANYA terhubung ke Brave via CDP (Remote Debugging).

    Sebelum menjalankan agent, pastikan Brave sudah dibuka di Windows dengan:
        cmd /c start brave --remote-debugging-port=9222

    Atau atur BRAVE_CDP_URL di .env jika port/host berbeda.
    Default endpoint: http://localhost:9222 (otomatis dikonversi ke IP Windows di WSL2).
    """

    def __init__(self, headless=False, use_camoufox=False, proxy=None,
                 endpoint_url="http://localhost:9222"):
        self.proxy = proxy
        self.endpoint_url = _resolve_brave_cdp_url(endpoint_url)

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.cursor = None

    def _init_browser(self):
        logging.info(f"Menghubungkan ke Brave via CDP: {self.endpoint_url}")
        logging.info("Pastikan Brave sudah berjalan dengan:")
        logging.info("  cmd /c start brave --remote-debugging-port=9222")

        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.connect_over_cdp(self.endpoint_url)

            if not self.browser.contexts:
                raise RuntimeError(
                    "Brave terhubung tapi tidak ada context/tab aktif. "
                    "Buka minimal satu tab di Brave, lalu coba lagi."
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

            logging.info(f"Berhasil terhubung ke Brave. Tab aktif: {self.page.url}")

        except Exception as e:
            self._cleanup_playwright()
            raise RuntimeError(
                f"Gagal konek ke Brave di {self.endpoint_url}.\n"
                f"Error: {e}\n\n"
                f"Solusi:\n"
                f"  1. Tutup semua proses Brave yang sedang berjalan.\n"
                f"  2. Buka Brave dengan perintah berikut di CMD Windows:\n"
                f"       cmd /c start brave --remote-debugging-port=9222\n"
                f"  3. Tunggu Brave terbuka, lalu jalankan agent lagi.\n"
                f"  4. Atau atur BRAVE_CDP_URL di file .env jika menggunakan port lain."
            ) from e

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
            if self.context:
                self.context.close()
        except Exception as e:
            logging.error(f"Error closing context: {e}")
        finally:
            self._cleanup_playwright()
            gc.collect()
            logging.info("Koneksi CDP ke Brave ditutup dan memori dibersihkan.")

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
