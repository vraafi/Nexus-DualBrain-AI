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
    Agent browser yang terhubung ke Brave via CDP (Remote Debugging).
    
    FITUR RESILIENSI:
    - Auto-reconnect jika koneksi CDP terputus (misal user pegang Brave)
    - Buat tab DEDIKASI untuk agent — user bisa pakai tab lain tanpa ganggu agent
    - Retry otomatis pada setiap operasi (navigate, click, type)
    
    Sebelum menjalankan agent, buka Brave di Windows dengan:
        cmd /c start brave --remote-debugging-port=9222
    """

    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_DELAY = 3  # detik

    def __init__(self, headless=False, use_camoufox=False, proxy=None,
                 endpoint_url="http://localhost:9222", llm_client=None):
        self.proxy = proxy
        self._base_url = endpoint_url
        self.endpoint_url = None
        self.llm = llm_client

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

        # Pakai tab pertama yang sudah ada — JANGAN buat tab baru
        # Tab baru menumpuk di Brave dan membingungkan user
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        self.page.set_default_timeout(60000)

        if GHOST_CURSOR_AVAILABLE:
            try:
                self.cursor = create_cursor(self.page)
            except Exception as e:
                logging.warning(f"Ghost cursor gagal init: {e}. Pakai standard click.")
                self.cursor = None
        else:
            self.cursor = None

        logging.info(f"Terhubung ke Brave via {self.endpoint_url}. Tab: {self.page.url}")
        self._inject_antigravity_overlay()
        self.set_agent_state("WORKING")

    def _inject_antigravity_overlay(self):
        """Menyuntikkan UI Antigravity (Bulatan Merah/Hijau & Blocker) ke halaman."""
        try:
            # Gunakan add_init_script pada level CONTEXT agar otomatis muncul di semua tab baru (termasuk yang dibuat main.py)
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
            logging.warning(f"Gagal injeksi overlay: {e}")

    def set_agent_state(self, state: str, message: str = ""):
        """Mengubah warna bulatan dan status bloker (WORKING = Merah/Kunci, WAITING = Hijau/Bebas)."""
        try:
            color = '#ff4444' if state == 'WORKING' else '#00C851'
            blocker_display = 'block' if state == 'WORKING' else 'none'
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
        """Pause agent, beri warna hijau, tunggu user selesai (cek URL setiap 5 detik)."""
        logging.warning(f"🚨 [AI PAUSED] Agent meminta bantuan Anda: {reason}")
        self.set_agent_state("WAITING", reason)
        
        # Tunggu maksimal 10 menit, tapi cek setiap 5 detik apakah sudah login
        max_wait = 600
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(5)
            elapsed += 5
            try:
                current_url = self.page.url.lower()
                # Jika sudah tidak ada kata 'login', 'challenge', atau 'signup', asumsikan sudah masuk
                if "login" not in current_url and "challenge" not in current_url and "signup" not in current_url:
                    logging.info("✅ [AI DETECTED] Deteksi otomatis: Anda sepertinya sudah berhasil login!")
                    break
            except Exception:
                pass
            
            if elapsed % 60 == 0:
                logging.info(f"Masih menunggu bantuan Anda... ({elapsed//60} menit berlalu)")

        logging.info("🤖 [AI RESUMED] Agent kembali mengambil alih!")
        self.set_agent_state("WORKING")

    def _is_connected(self) -> bool:
        """Cek apakah koneksi CDP masih hidup."""
        try:
            if not self.page or not self.browser:
                return False
            # Test koneksi dengan operasi ringan
            _ = self.page.url
            return True
        except Exception:
            return False

    def _reconnect(self) -> bool:
        """
        Auto-reconnect ke Brave jika koneksi terputus.
        Dicoba hingga MAX_RECONNECT_ATTEMPTS kali.
        """
        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            logging.warning(
                "[BrowserAgent] Koneksi terputus. Reconnect attempt %d/%d...",
                attempt, self.MAX_RECONNECT_ATTEMPTS
            )
            try:
                # Bersihkan koneksi lama
                self._cleanup_playwright()
                time.sleep(self.RECONNECT_DELAY)

                # Coba konek ulang
                self._init_browser()
                logging.info("[BrowserAgent] ✅ Reconnect berhasil!")
                return True
            except Exception as e:
                logging.error("[BrowserAgent] Reconnect attempt %d gagal: %s", attempt, e)
                time.sleep(self.RECONNECT_DELAY * attempt)

        logging.error("[BrowserAgent] ❌ Semua reconnect attempt gagal.")
        return False

    def _ensure_connected(self) -> bool:
        """
        Pastikan koneksi CDP aktif. Jika terputus, otomatis reconnect.
        Dipanggil sebelum setiap operasi browser.
        """
        if self._is_connected():
            return True
        return self._reconnect()

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
        """
        Ketik teks ke elemen. JANGAN reconnect jika locator timeout —
        itu artinya elemen tidak ditemukan, bukan koneksi putus.
        Reconnect hanya jika koneksi benar-benar mati.

        PENTING: Setelah reconnect, locator LAMA sudah MATI (bound ke
        Playwright instance lama). Jangan coba pakai locator lama.
        """
        if not self._ensure_connected():
            logging.error("Tidak bisa type — koneksi Brave terputus.")
            return
        try:
            locator.click()
            self._human_delay(500, 1000)
            locator.press_sequentially(text, delay=100)
        except Exception as e:
            logging.error(f"Failed during human_type: {e}")
            if self.llm:
                logging.info("🧠 Menjalankan Visual Reasoning Fallback untuk mengetik...")
                if self.visual_action_fallback(f"input field for: {locator}", action_type="type", text_to_type=text):
                    return

            if not self._is_connected():
                logging.warning("Koneksi mati. Reconnect diperlukan.")
                self._reconnect()
            else:
                try:
                    locator.fill(text)
                except Exception:
                    pass

    def human_click(self, selector):
        """
        Klik elemen. Menerima string CSS selector ATAU Playwright Locator.
        Fitur Antigravity: Jika gagal, agent akan berubah hijau dan meminta bantuan user,
        kemudian mengulanginya lagi tanpa terputus.
        """
        if not self._ensure_connected():
            logging.error("Tidak bisa click — koneksi Brave terputus.")
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
                return  # Berhasil, keluar dari fungsi
            except Exception as e:
                logging.warning(f"Click gagal (Attempt {attempt}): {e}")
                if attempt == 2 and self.llm:
                    logging.info("🧠 Menjalankan Visual Reasoning Fallback untuk klik...")
                    target_desc = f"button or link related to: {selector}" if not is_locator else "the targeted element in the instruction"
                    if self.visual_action_fallback(target_desc, action_type="click"):
                        return

                if attempt < 3:
                    self.request_human_help(f"Gagal klik elemen. Silakan klik secara manual di browser, atau tunggu saya mencoba lagi dalam 30 detik.")
                else:
                    logging.error("Gagal klik setelah 3x percobaan Antigravity. Melanjutkan...")
                    if not self._is_connected():
                        self._reconnect()

    def visual_action_fallback(self, target_description: str, action_type="click", text_to_type=None) -> bool:
        """
        Gunakan Vision AI (Gemini) untuk menemukan koordinat elemen berdasarkan screenshot.
        """
        if not self.llm:
            return False

        try:
            temp_screenshot = "visual_fallback.jpg"
            self.page.screenshot(path=temp_screenshot, type="jpeg", quality=80)
            
            import base64
            with open(temp_screenshot, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            
            viewport = self.page.viewport_size
            prompt = (
                f"You are a visual web automation assistant. Look at the screenshot of the current webpage. "
                f"Identify the (x, y) coordinates for the following target: '{target_description}'. "
                f"Return ONLY a JSON object with 'x' and 'y' keys (values in pixels relative to top-left). "
                f"The current viewport size is {viewport['width']}x{viewport['height']}. "
                "Ensure coordinates are precisely on the interactive center of the element."
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
                    logging.info(f"🧠 Vision AI menemukan target di ({x}, {y}). Melakukan {action_type}...")
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
            logging.error(f"Visual reasoning fallback failed: {e}")
            
            # LAST RESORT: Keyboard Navigation Fallback (Suggested by user: "keyboard untuk orang buta")
            try:
                logging.info("⌨️ Visual gagal. Mencoba Keyboard Navigation Fallback (TAB/ENTER)...")
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
        """
        Navigasi ke URL dengan strategi loading progresif.

        Strategi (diurutkan dari cepat ke lambat):
          1. goto() + wait domcontentloaded (HTML parsed, cukup untuk automation)
          2. Jika timeout: reconnect + retry dengan timeout lebih panjang
          3. Jika tetap gagal: coba tanpa wait (halaman mungkin partially loaded)

        CATATAN: JANGAN pakai 'networkidle' — situs seperti Fiverr/Upwork punya
        tracker, analytics, dan websocket yang TIDAK PERNAH berhenti.
        'networkidle' akan selalu timeout di situs berat.
        """
        if not self._ensure_connected():
            logging.error(f"Tidak bisa navigate ke {url} — koneksi Brave terputus.")
            return False
        try:
            self._human_delay()
            self.page.goto(url, timeout=45000, wait_until="domcontentloaded")
            self._human_delay(2000, 4000)
            return True
        except Exception as e:
            logging.warning(f"Navigate ke {url} gagal (attempt 1): {e}")

            # Coba reconnect lalu retry dengan timeout lebih panjang
            if self._reconnect():
                try:
                    self.page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    self._human_delay(2000, 4000)
                    return True
                except Exception as e2:
                    logging.warning(f"Navigate retry gagal (attempt 2): {e2}")

                    # Fallback terakhir: coba tanpa wait — halaman mungkin cukup loaded
                    try:
                        self.page.goto(url, timeout=60000, wait_until="commit")
                        # Tunggu manual 5 detik agar halaman partially load
                        time.sleep(5)
                        logging.info(f"Navigate ke {url} berhasil (partial load).")
                        return True
                    except Exception as e3:
                        logging.error(f"Navigate gagal total ke {url}: {e3}")

            return False

    def navigate_to_safe_page(self):
        """
        Navigasi ke halaman netral sebelum disconnect (untuk rest hours).
        Brave tetap terbuka di halaman aman, bukan di Upwork/Fiverr.
        """
        try:
            if self.page and self._is_connected():
                self.page.goto("https://www.google.com", timeout=15000)
                logging.info("Browser dinavigasi ke halaman netral (Google).")
        except Exception as e:
            logging.warning(f"Gagal navigasi ke safe page: {e}")

    def quit(self):
        """
        Lepaskan koneksi CDP ke Brave TANPA menutup tab.
        Brave tetap hidup dengan tab yang ada.
        """
        try:
            pass  # Jangan tutup tab apapun — Brave harus tetap hidup
        except Exception as e:
            logging.error(f"Error during quit: {e}")
        finally:
            self._cleanup_playwright()
            gc.collect()
            logging.info("Koneksi CDP dilepas. Brave tetap terbuka.")

    def deep_search(self, query: str) -> str:
        """
        Melakukan pencarian mendalam dengan benar-benar membuka Google di browser Brave.
        Berguna sebagai cadangan jika pencarian API tidak cukup detail.
        """
        self.logger.info(f"🔍 [BrowserAgent] Memulai Deep Search di Brave: '{query}'")
        if not self._ensure_connected():
            return "Gagal Deep Search: Koneksi browser terputus."

        original_url = self.page.url
        search_tab = None
        try:
            # Buka tab baru untuk pencarian agar tidak mengganggu tab utama
            search_tab = self.context.new_page()
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            search_tab.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(3) # Tunggu hasil render

            # Ekstrak teks dari hasil pencarian utama
            # Biasanya ada di div dengan class 'g' atau 'v7W49e'
            results = search_tab.locator("div.g").all()
            snippets = []
            for res in results[:5]: # Ambil 5 hasil teratas
                text = res.inner_text().strip()
                if text:
                    snippets.append(text)

            if not snippets:
                # Fallback: ambil semua teks body jika selector gagal
                body_text = search_tab.inner_text("body")
                summary = body_text[:2000] # Ambil 2000 karakter pertama
            else:
                summary = "\n---\n".join(snippets)

            self.logger.info(f"✅ [BrowserAgent] Deep Search selesai. Berhasil mendapatkan {len(snippets)} cuplikan.")
            return summary

        except Exception as e:
            self.logger.error(f"❌ [BrowserAgent] Deep Search gagal: {e}")
            return f"Error saat Deep Search: {e}"
        finally:
            if search_tab:
                search_tab.close()
            # Pastikan kembali ke tab utama
            self.page.bring_to_front()

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()

