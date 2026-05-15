"""
browser_agent.py — Nexus DualBrain AI
========================================
Dual-mode browser agent:

  MODE 1 (default): CDP connection ke Brave yang sudah berjalan.
    → Buka Brave dengan: cmd /c start brave --remote-debugging-port=9222
    → Set .env: USE_CAMOUFOX=false  (atau tidak di-set)

  MODE 2 (stealth): Camoufox — Firefox fork dengan fingerprint spoofing di level C++.
    → Set .env: USE_CAMOUFOX=true
    → Tidak butuh Brave. Agent buka/tutup browser sendiri.
    → Fingerprint (User-Agent, OS, timezone, canvas, WebGL, fonts) dispoof di
      level implementasi C++, bukan JavaScript injection — tidak terdeteksi.
    → ~200MB vs Chrome 800MB+. Cocok untuk server/VPS.

Pilih mode:
  USE_CAMOUFOX=false  → CDP ke Brave (user bisa lihat AI bekerja real-time)
  USE_CAMOUFOX=true   → Camoufox headless stealth (ideal untuk server/undetected)
"""

import gc
import logging
import time
import random
import os
import subprocess
from playwright.sync_api import sync_playwright

try:
    from camoufox.sync_api import Camoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    logging.warning("camoufox tidak terinstall. Jalankan: pip install camoufox==0.4.11 && python -m camoufox fetch")

try:
    from python_ghost_cursor.playwright_sync import create_cursor
    GHOST_CURSOR_AVAILABLE = True
except ImportError:
    GHOST_CURSOR_AVAILABLE = False
    logging.warning("python-ghost-cursor tidak tersedia. Fallback ke standard click.")


def _get_cdp_candidates(base_url: str) -> list:
    port = base_url.split(":")[-1].strip("/")

    override = os.environ.get("BRAVE_CDP_URL", "").strip()
    if override:
        logging.info(f"BRAVE_CDP_URL dari env: {override}")
        return [override]

    candidates = []
    candidates.append(f"http://localhost:{port}")

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


_CAMOUFOX_LOCALES = [
    ("en-US", "America/New_York"),
    ("en-US", "America/Chicago"),
    ("en-US", "America/Los_Angeles"),
    ("en-GB", "Europe/London"),
    ("en-AU", "Australia/Sydney"),
    ("en-CA", "America/Toronto"),
]

def _pick_random_locale():
    return random.choice(_CAMOUFOX_LOCALES)


class BrowserAgent:
    """
    Agent browser dual-mode: Brave CDP (default) atau Camoufox stealth.

    BRAVE CDP MODE (USE_CAMOUFOX=false):
    - Konek ke Brave yang sudah running via Chrome DevTools Protocol
    - User bisa lihat apa yang dikerjakan AI real-time
    - Anti-gravity overlay (merah/hijau) menampilkan status agent
    - Auto-reconnect jika koneksi terputus

    CAMOUFOX MODE (USE_CAMOUFOX=true):
    - Firefox fork dengan C++-level fingerprint spoofing
    - Tidak ada jejak JavaScript injection yang bisa dideteksi
    - User-Agent, OS, timezone, canvas, WebGL, fonts dispoof otomatis
    - Headless by default, ~200MB footprint
    - Ideal untuk deployment server/VPS atau saat Brave tidak available
    """

    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_DELAY = 3

    def __init__(self, headless=False, use_camoufox=None, proxy=None,
                 endpoint_url="http://localhost:9222", llm_client=None):
        self.proxy = proxy
        self._base_url = endpoint_url
        self.endpoint_url = None
        self.llm = llm_client
        self.logger = logging.getLogger(__name__)

        if use_camoufox is None:
            env_val = os.environ.get("USE_CAMOUFOX", "false").strip().lower()
            use_camoufox = env_val in ("1", "true", "yes")

        self._use_camoufox = use_camoufox and CAMOUFOX_AVAILABLE
        self._headless = headless

        if use_camoufox and not CAMOUFOX_AVAILABLE:
            self.logger.warning(
                "USE_CAMOUFOX=true tapi camoufox belum terinstall. "
                "Fallback ke CDP Brave. "
                "Install: pip install camoufox==0.4.11 && python -m camoufox fetch"
            )

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.cursor = None
        self._camoufox_instance = None

        mode_label = "Camoufox (stealth)" if self._use_camoufox else "Brave CDP"
        self.logger.info("[BrowserAgent] Mode: %s", mode_label)

    def _init_camoufox(self):
        """
        Inisialisasi Camoufox. Firefox fork dengan fingerprint spoofing di level C++.

        Camoufox secara otomatis:
        - Spoof User-Agent (random versi Firefox yang valid)
        - Spoof OS (Linux/Windows/macOS secara konsisten di semua API)
        - Spoof canvas noise (anti-canvas fingerprint)
        - Spoof WebGL (vendor, renderer string)
        - Spoof font list, screen resolution, color depth
        - Spoof timezone dan locale sesuai parameter
        - Blok WebRTC leaks
        - Randomize audio context fingerprint
        """
        if not CAMOUFOX_AVAILABLE:
            raise RuntimeError(
                "Camoufox tidak terinstall. Jalankan:\
"
                "  pip install camoufox==0.4.11\
"
                "  python -m camoufox fetch\
"
                "Atau set USE_CAMOUFOX=false untuk pakai Brave CDP."
            )

        locale, timezone = _pick_random_locale()
        self.logger.info(
            "[Camoufox] Memulai browser stealth... locale=%s, tz=%s, headless=%s",
            locale, timezone, self._headless
        )

        proxy_config = None
        if self.proxy:
            proxy_config = {"server": self.proxy}

        self._camoufox_instance = Camoufox(
            headless=self._headless,
            locale=locale,
            proxy=proxy_config,
            geoip=bool(self.proxy),
            humanize=True,
            block_images=False,
            block_webrtc=True,
            os="windows",
        )

        self.browser = self._camoufox_instance.__enter__()
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.set_default_timeout(60000)

        if GHOST_CURSOR_AVAILABLE:
            try:
                self.cursor = create_cursor(self.page)
            except Exception:
                self.cursor = None

        self.logger.info(
            "[Camoufox] Browser stealth aktif. locale=%s, tz=%s", locale, timezone
        )

    def _try_connect(self, url: str) -> bool:
        try:
            self.logger.info("Mencoba konek ke Brave: %s ...", url)
            pw = sync_playwright().start()
            browser = pw.chromium.connect_over_cdp(url, timeout=30000)
            if not browser.contexts:
                pw.stop()
                self.logger.warning("%s terhubung tapi tidak ada tab aktif.", url)
                return False
            self.playwright = pw
            self.browser = browser
            self.endpoint_url = url
            return True
        except Exception as e:
            self.logger.warning("Gagal konek ke %s: %s", url, e)
            try:
                pw.stop()
            except Exception:
                pass
            return False

    def _init_brave_cdp(self):
        candidates = _get_cdp_candidates(self._base_url)
        self.logger.info("Urutan endpoint yang akan dicoba: %s", candidates)
        self.logger.info("Pastikan Brave sudah berjalan dengan:")
        self.logger.info("  cmd /c start brave --remote-debugging-port=9222")

        connected = False
        for url in candidates:
            if self._try_connect(url):
                connected = True
                break

        if not connected:
            raise RuntimeError(
                f"Gagal konek ke Brave di semua endpoint: {candidates}\
\
"
                f"Solusi:\
"
                f"  1. Tutup semua proses Brave (Task Manager).\
"
                f"  2. Buka CMD Windows:\
"
                f"       cmd /c start brave --remote-debugging-port=9222\
"
                f"  3. Tunggu Brave terbuka sempurna (ada minimal 1 tab).\
"
                f"  4. Jalankan agent lagi.\
\
"
                f"  Jika tetap gagal, tambahkan di .env:\
"
                f"       BRAVE_CDP_URL=http://localhost:9222\
\
"
                f"  Atau aktifkan Camoufox:\
"
                f"       USE_CAMOUFOX=true\
"
                f"       pip install camoufox==0.4.11 && python -m camoufox fetch"
            )

        self.context = self.browser.contexts[0]

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        self.page.set_default_timeout(60000)

        if GHOST_CURSOR_AVAILABLE:
            try:
                self.cursor = create_cursor(self.page)
            except Exception as e:
                self.logger.warning("Ghost cursor gagal init: %s. Pakai standard click.", e)
                self.cursor = None
        else:
            self.cursor = None

        self.logger.info(
            "Terhubung ke Brave via %s. Tab: %s", self.endpoint_url, self.page.url
        )
        self._inject_antigravity_overlay()
        self.set_agent_state("WORKING")

    def _init_browser(self):
        if self._use_camoufox:
            self._init_camoufox()
        else:
            self._init_brave_cdp()

    def _inject_antigravity_overlay(self):
        """Inject UI Anti-gravity (bulatan merah/hijau) ke halaman Brave."""
        if self._use_camoufox:
            return
        try:
            self.context.add_init_script('''
                window.nexusInjectOverlay = function() {
                    if(document.getElementById('nexus-agent-overlay')) return;
                    const indicator = document.createElement('div');
                    indicator.id = 'nexus-agent-overlay';
                    indicator.style.cssText = 'position:fixed; bottom:20px; right:20px; width:60px; height:60px; background-color:#ff4444; border-radius:50%; z-index:2147483647; box-shadow: 0 0 20px #ff4444; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold; font-family:sans-serif; font-size:14px; transition: all 0.3s ease; cursor:pointer; user-select:none;';
                    indicator.innerText = 'AI';
                    document.body.appendChild(indicator);
                };
                window.addEventListener('load', window.nexusInjectOverlay);
                window.addEventListener('DOMContentLoaded', window.nexusInjectOverlay);
            ''')
            self.page.evaluate('window.nexusInjectOverlay && window.nexusInjectOverlay()')
        except Exception as e:
            self.logger.warning("Gagal injeksi overlay: %s", e)

    def set_agent_state(self, state: str, message: str = ""):
        """Ubah warna bulatan (WORKING=Merah, WAITING=Hijau). Hanya di Brave CDP mode."""
        if self._use_camoufox:
            return
        try:
            color = '#ff4444' if state == 'WORKING' else '#00C851'
            text = 'AI' if state == 'WORKING' else 'USER'
            self.page.evaluate(f'''() => {{
                const ind = document.getElementById('nexus-agent-overlay');
                if(ind) {{
                    ind.style.backgroundColor = '{color}';
                    ind.innerText = '{text}';
                    ind.style.boxShadow = '0 0 20px {color}';
                    if('{message}') ind.title = '{message}';
                }}
            }}''')
        except Exception:
            pass

    def request_human_help(self, reason: str = "Butuh bantuan CAPTCHA/Login"):
        """
        Pause agent, minta bantuan user.
        Brave CDP: ubah overlay ke hijau, tunggu URL berubah.
        Camoufox: log warning + auto-retry setelah 30 detik.
        """
        if self._use_camoufox:
            self.logger.warning(
                "[Camoufox] Butuh intervensi manual: %s\
"
                "Camoufox berjalan headless. Coba lagi dalam 30 detik...", reason
            )
            time.sleep(30)
            return

        self.logger.warning("[AI PAUSED] Agent meminta bantuan Anda: %s", reason)
        self.set_agent_state("WAITING", reason)

        max_wait = 600
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(5)
            elapsed += 5
            try:
                current_url = self.page.url.lower()
                if "login" not in current_url and "challenge" not in current_url and "signup" not in current_url:
                    self.logger.info("[AI DETECTED] Deteksi otomatis: sudah berhasil login!")
                    break
            except Exception:
                pass
            if elapsed % 60 == 0:
                self.logger.info("Masih menunggu bantuan Anda... (%d menit berlalu)", elapsed // 60)

        self.logger.info("[AI RESUMED] Agent kembali mengambil alih!")
        self.set_agent_state("WORKING")

    def _is_connected(self) -> bool:
        try:
            if not self.page or not self.browser:
                return False
            _ = self.page.url
            return True
        except Exception:
            return False

    def _reconnect(self) -> bool:
        """Auto-reconnect ke Brave (hanya CDP mode). Camoufox tidak perlu reconnect."""
        if self._use_camoufox:
            return self._is_connected()

        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            self.logger.warning(
                "[BrowserAgent] Koneksi terputus. Reconnect attempt %d/%d...",
                attempt, self.MAX_RECONNECT_ATTEMPTS
            )
            try:
                self._cleanup_playwright()
                time.sleep(self.RECONNECT_DELAY)
                self._init_brave_cdp()
                self.logger.info("[BrowserAgent] Reconnect berhasil!")
                return True
            except Exception as e:
                self.logger.error("[BrowserAgent] Reconnect attempt %d gagal: %s", attempt, e)
                time.sleep(self.RECONNECT_DELAY * attempt)

        self.logger.error("[BrowserAgent] Semua reconnect attempt gagal.")
        return False

    def _ensure_connected(self) -> bool:
        if self._is_connected():
            return True
        if self._use_camoufox:
            self.logger.error("[Camoufox] Koneksi page hilang. Tidak bisa auto-reconnect.")
            return False
        return self._reconnect()

    def _cleanup_playwright(self):
        try:
            if self._camoufox_instance:
                try:
                    self._camoufox_instance.__exit__(None, None, None)
                except Exception:
                    pass
                self._camoufox_instance = None
            elif self.playwright:
                try:
                    self.playwright.stop()
                except Exception:
                    pass
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
        """Ketik teks ke elemen dengan delay antar-karakter yang natural."""
        if not self._ensure_connected():
            self.logger.error("Tidak bisa type \u2014 koneksi browser terputus.")
            return
        try:
            locator.click()
            self._human_delay(500, 1000)
            locator.press_sequentially(text, delay=random.randint(80, 150))
        except Exception as e:
            self.logger.error("Failed during human_type: %s", e)
            if self.llm:
                self.logger.info("Menjalankan Visual Reasoning Fallback untuk mengetik...")
                if self.visual_action_fallback(
                    f"input field for: {locator}", action_type="type", text_to_type=text
                ):
                    return

            if not self._is_connected():
                self.logger.warning("Koneksi mati. Reconnect diperlukan.")
                self._reconnect()
            else:
                try:
                    locator.fill(text)
                except Exception:
                    pass

    def human_click(self, selector):
        """
        Klik elemen. Menerima CSS selector string ATAU Playwright Locator.
        Jika gagal 2x, jalankan Visual Reasoning Fallback (screenshot + LLM).
        Jika gagal 3x, request human help (Brave) atau log warning (Camoufox).
        """
        if not self._ensure_connected():
            self.logger.error("Tidak bisa click \u2014 koneksi browser terputus.")
            return

        from playwright.sync_api import Locator
        is_locator = isinstance(selector, Locator)
        for attempt in range(1, 4):
            try:
                if is_locator:
                    selector.scroll_into_view_if_needed(timeout=10000)
                    if self.cursor is not None:
                        box = selector.bounding_box()
                        if box:
                            cx = box["x"] + box["width"] / 2
                            cy = box["y"] + box["height"] / 2
                            self.page.mouse.click(cx, cy)
                        else:
                            selector.click(timeout=10000)
                    else:
                        selector.click(timeout=10000)
                else:
                    if self.cursor is not None:
                        self.cursor.click(selector)
                    else:
                        self.page.click(selector, timeout=10000)
                return
            except Exception as e:
                self.logger.warning("Click gagal (Attempt %d): %s", attempt, e)
                if attempt == 2 and self.llm:
                    self.logger.info("Menjalankan Visual Reasoning Fallback untuk klik...")
                    target_desc = (
                        f"button or link related to: {selector}"
                        if not is_locator
                        else "the targeted element in the instruction"
                    )
                    if self.visual_action_fallback(target_desc, action_type="click"):
                        return

                if attempt < 3:
                    self.request_human_help(
                        "Gagal klik elemen. Silakan klik secara manual, "
                        "atau tunggu saya mencoba lagi dalam 30 detik."
                    )
                else:
                    self.logger.error("Gagal klik setelah 3x percobaan. Melanjutkan...")
                    if not self._use_camoufox and not self._is_connected():
                        self._reconnect()

    def visual_action_fallback(self, target_description: str, action_type="click", text_to_type=None) -> bool:
        """Gunakan Vision AI (Gemini) untuk menemukan koordinat elemen berdasarkan screenshot."""
        if not self.llm:
            return False

        try:
            temp_screenshot = "visual_fallback.jpg"
            self.page.screenshot(path=temp_screenshot, type="jpeg", quality=80)

            import base64
            with open(temp_screenshot, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")

            viewport = self.page.viewport_size or {'width': 1280, 'height': 720}
            prompt = (
                f"You are a visual web automation assistant. Look at the screenshot. "
                f"Identify the (x, y) coordinates for: '{target_description}'. "
                f"Return ONLY JSON: {{\"x\": int, \"y\": int}}. "
                f"Viewport: {viewport['width']}x{viewport['height']}. "
                "Coordinates must be on the interactive center of the element."
            )

            res = self.llm.generate_content(prompt, image_base64=img_data, require_json=True)
            if res:
                if "```json" in res:
                    res = res.split("```json")[1].split("```")[0].strip()
                elif "```" in res:
                    res = res.split("```")[1].strip()

                import json
                coords = json.loads(res)
                x, y = coords.get("x"), coords.get("y")

                if x is not None and y is not None:
                    self.logger.info(
                        "Vision AI menemukan target di (%s, %s). Melakukan %s...", x, y, action_type
                    )
                    self.page.mouse.click(x, y)
                    if action_type == "type" and text_to_type:
                        time.sleep(1)
                        self.page.keyboard.type(text_to_type, delay=random.randint(50, 150))

                    try:
                        os.remove(temp_screenshot)
                    except Exception:
                        pass
                    return True

            return False
        except Exception as e:
            self.logger.error("Visual reasoning fallback failed: %s", e)
            try:
                self.logger.info("Visual gagal. Mencoba Keyboard Navigation Fallback (TAB/ENTER)...")
                self.page.keyboard.press("Tab")
                time.sleep(0.5)
                if action_type == "click":
                    self.page.keyboard.press("Enter")
                elif action_type == "type" and text_to_type:
                    self.page.keyboard.type(text_to_type)
                    self.page.keyboard.press("Enter")
                return True
            except Exception:
                return False

    def navigate(self, url):
        """Navigasi ke URL. Hindari networkidle \u2014 situs berat tidak pernah idle."""
        if not self._ensure_connected():
            self.logger.error("Tidak bisa navigate ke %s \u2014 koneksi browser terputus.", url)
            return False
        try:
            self._human_delay()
            self.page.goto(url, timeout=45000, wait_until="domcontentloaded")
            self._human_delay(2000, 4000)
            return True
        except Exception as e:
            self.logger.warning("Navigate ke %s gagal (attempt 1): %s", url, e)

            if not self._use_camoufox and self._reconnect():
                try:
                    self.page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    self._human_delay(2000, 4000)
                    return True
                except Exception as e2:
                    self.logger.warning("Navigate retry gagal (attempt 2): %s", e2)
                    try:
                        self.page.goto(url, timeout=60000, wait_until="commit")
                        time.sleep(5)
                        self.logger.info("Navigate ke %s berhasil (partial load).", url)
                        return True
                    except Exception as e3:
                        self.logger.error("Navigate gagal total ke %s: %s", url, e3)

            return False

    def navigate_to_safe_page(self):
        """Navigasi ke halaman netral sebelum disconnect (untuk rest hours)."""
        try:
            if self.page and self._is_connected():
                self.page.goto("https://www.google.com", timeout=15000)
                self.logger.info("Browser dinavigasi ke halaman netral (Google).")
        except Exception as e:
            self.logger.warning("Gagal navigasi ke safe page: %s", e)

    def quit(self):
        """Brave CDP: lepas koneksi tanpa tutup tab. Camoufox: tutup browser."""
        try:
            if self._use_camoufox:
                self.logger.info("Menutup Camoufox browser...")
            else:
                self.logger.info("Melepas koneksi CDP. Brave tetap terbuka.")
        except Exception as e:
            self.logger.error("Error during quit: %s", e)
        finally:
            self._cleanup_playwright()
            gc.collect()

    def deep_search(self, query: str) -> str:
        """Lakukan pencarian mendalam dengan membuka Google di browser."""
        self.logger.info("[BrowserAgent] Deep Search: '%s'", query)
        if not self._ensure_connected():
            return "Gagal Deep Search: Koneksi browser terputus."

        search_tab = None
        try:
            search_tab = self.context.new_page()
            search_url = "https://www.google.com/search?q=" + query.replace(" ", "+")
            search_tab.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(3)

            results = search_tab.locator("div.g").all()
            snippets = []
            for res in results[:5]:
                text = res.inner_text().strip()
                if text:
                    snippets.append(text)

            if not snippets:
                body_text = search_tab.inner_text("body")
                summary = body_text[:2000]
            else:
                summary = "\
---\
".join(snippets)

            self.logger.info("[BrowserAgent] Deep Search selesai. %d cuplikan.", len(snippets))
            return summary

        except Exception as e:
            self.logger.error("[BrowserAgent] Deep Search gagal: %s", e)
            return f"Error saat Deep Search: {e}"
        finally:
            if search_tab:
                try:
                    search_tab.close()
                except Exception:
                    pass
            try:
                if self.page:
                    self.page.bring_to_front()
            except Exception:
                pass

    def get_page_text(self, url: str = None) -> str:
        """Ambil teks dari halaman saat ini (atau navigasi ke URL dulu)."""
        if url:
            self.navigate(url)
        try:
            return self.page.inner_text("body", timeout=10000)
        except Exception as e:
            self.logger.error("Gagal ambil page text: %s", e)
            return ""

    def screenshot(self, path: str = "screenshot.jpg") -> bool:
        """Ambil screenshot halaman saat ini."""
        try:
            self.page.screenshot(path=path, type="jpeg", quality=85)
            return True
        except Exception as e:
            self.logger.error("Gagal screenshot: %s", e)
            return False

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
