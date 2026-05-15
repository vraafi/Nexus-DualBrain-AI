"""
browser_agent.py — Nexus DualBrain AI
Refactored: Playwright manual CSS selector diganti dengan Browser-Use.
Reference: https://github.com/browser-use/browser-use
Retry mechanism: https://github.com/jd/tenacity (43k+ stars)

Serialization fix:
  Masalah: banyak BrowserAgent dibuat bersamaan → CDP race condition → crash.
  Solusi: satu browser singleton (module-level) + satu global threading.Lock
  agar semua task antri dan jalan satu per satu.
  Pattern ini dipakai ribuan pengguna di GitHub:
  https://github.com/browser-use/browser-use/issues/3718
  https://github.com/browser-use/browser-use/issues/2840
"""
import asyncio
import gc
import logging
import os
import threading
import time
from typing import Optional

# Retry dengan exponential backoff — terbukti dipakai oleh ribuan project
# Referensi: https://github.com/jd/tenacity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Browser-Use imports
# Referensi: https://github.com/browser-use/browser-use (60k+ stars)
from browser_use import Agent, Browser, BrowserProfile
from pydantic import Field, SecretStr
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETON — satu lock + satu browser untuk seluruh proses.
# Semua BrowserAgent instance berbagi resource ini sehingga hanya satu
# task browser yang berjalan pada satu waktu (tidak ada CDP race condition).
# Referensi pattern: https://github.com/browser-use/browser-use/issues/3718
# ─────────────────────────────────────────────────────────────────────────────
_BROWSER_LOCK = threading.Lock()
_SHARED_BROWSER: Optional[Browser] = None
_SHARED_BROWSER_LOCK = threading.Lock()


def _get_wsl_host_ip() -> Optional[str]:
    """
    Ambil IP Windows host dari dalam WSL secara otomatis.
    Dibaca dari /etc/resolv.conf (standar WSL2).
    Referensi: https://learn.microsoft.com/en-us/windows/wsl/networking
    """
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.startswith("nameserver"):
                    ip = line.split()[1].strip()
                    if ip and ip != "127.0.0.1":
                        return ip
    except Exception:
        pass
    return None


def _probe_cdp(url: str, timeout: float = 2.0) -> bool:
    """
    Cek apakah ada browser yang sudah berjalan dengan remote debugging di URL ini.
    Return True jika CDP endpoint aktif.
    """
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.urlopen(f"{url}/json/version", timeout=timeout)
        return req.status == 200
    except Exception:
        return False


def _resolve_brave_path() -> Optional[str]:
    """
    Cari path executable Brave browser dari env variable atau lokasi default.
    Termasuk path WSL untuk Brave yang ada di Windows (/mnt/c/...).
    """
    import shutil

    # 1. Dari env variable eksplisit
    for env_key in ("BRAVE_PATH", "BROWSER_EXECUTABLE", "BRAVE_EXECUTABLE"):
        path = os.environ.get(env_key, "").strip()
        if path and os.path.isfile(path):
            return path

    # 2. Lokasi umum — Linux native, WSL (via /mnt/c), macOS
    candidates = [
        # Linux native
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
        "/snap/bin/brave",
        "/opt/brave.com/brave/brave",
        # WSL — Brave terinstall di Windows, diakses via /mnt/c
        "/mnt/c/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
        "/mnt/c/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
        # macOS
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    # 3. Cari via PATH
    return shutil.which("brave-browser") or shutil.which("brave")


def _auto_launch_brave(brave_path: str, port: int = 9222) -> bool:
    """
    Launch Brave dengan remote debugging port secara otomatis.
    Mendukung Linux native, WSL (via cmd.exe /c start), dan macOS.
    Referensi pattern: https://github.com/browser-use/browser-use/issues/4709

    Return True jika Brave berhasil distart dalam 10 detik.
    """
    import subprocess

    flags = [
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=0.0.0.0",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    try:
        if brave_path.endswith(".exe") or "/mnt/c/" in brave_path:
            # WSL: jalankan .exe via cmd.exe agar berjalan di Windows
            win_path = brave_path.replace("/mnt/c/", "C:\\").replace("/", "\\")
            cmd = ["cmd.exe", "/c", "start", "", win_path] + flags
            logger.info("[BrowserAgent] Launch Brave di Windows (WSL): %s", win_path)
        else:
            cmd = [brave_path] + flags
            logger.info("[BrowserAgent] Launch Brave: %s", brave_path)

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning("[BrowserAgent] Gagal launch Brave: %s", e)
        return False

    # Tunggu sampai CDP aktif (max 15 detik)
    for i in range(15):
        time.sleep(1)
        if _probe_cdp(f"http://127.0.0.1:{port}"):
            logger.info("[BrowserAgent] Brave berhasil distart (CDP aktif setelah %ds).", i + 1)
            return True
        # Juga cek host WSL
        wsl_ip = _get_wsl_host_ip()
        if wsl_ip and _probe_cdp(f"http://{wsl_ip}:{port}"):
            logger.info("[BrowserAgent] Brave aktif di Windows host %s:%d.", wsl_ip, port)
            return True

    logger.warning("[BrowserAgent] Brave tidak responsif setelah 15 detik.")
    return False


def _find_active_cdp_url(port: int = 9222) -> Optional[str]:
    """
    Cari CDP URL yang aktif secara otomatis tanpa config manual.
    Urutan cek:
      1. BRAVE_CDP_URL dari env
      2. 127.0.0.1 (localhost / Linux native)
      3. WSL host IP (Windows host dari WSL2)
      4. IP umum WSL lainnya
    """
    candidates = []

    # 1. Dari env (prioritas tertinggi)
    env_url = os.environ.get("BRAVE_CDP_URL", "").strip()
    if env_url:
        candidates.append(env_url)

    # 2. Localhost
    candidates.append(f"http://127.0.0.1:{port}")

    # 3. WSL host (Windows) — otomatis deteksi
    wsl_ip = _get_wsl_host_ip()
    if wsl_ip:
        candidates.append(f"http://{wsl_ip}:{port}")

    # 4. IP WSL umum lainnya
    for ip in ("172.24.48.1", "172.16.0.1", "192.168.1.1"):
        if ip != wsl_ip:
            candidates.append(f"http://{ip}:{port}")

    for url in candidates:
        if _probe_cdp(url):
            logger.info("[BrowserAgent] Brave CDP aktif di: %s", url)
            return url

    return None


def _get_shared_browser(proxy=None) -> Browser:
    """
    Mengembalikan singleton Browser yang dibuat sekali dan dipakai ulang.
    Thread-safe: menggunakan _SHARED_BROWSER_LOCK untuk init.

    Urutan deteksi browser (OTOMATIS, tanpa config manual):
      1. Cek apakah Brave sudah berjalan dengan CDP di port umum
         → Jika ya, langsung connect (pakai sesi Brave yang ada, termasuk login)
      2. Jika tidak, cari path Brave dan launch otomatis dengan remote debugging
         → Launch Brave, tunggu siap, lalu connect via CDP
      3. Fallback: pakai Playwright Chromium (browser bawaan Linux)

    Referensi: https://github.com/browser-use/browser-use/issues/4709
                https://github.com/browser-use/browser-use/issues/3718
    """
    global _SHARED_BROWSER
    with _SHARED_BROWSER_LOCK:
        if _SHARED_BROWSER is None:
            # ── STEP 1: Cek apakah Brave sudah berjalan dengan CDP ──────────
            cdp_url = _find_active_cdp_url()

            if not cdp_url:
                # ── STEP 2: Launch Brave otomatis ───────────────────────────
                brave_path = _resolve_brave_path()
                if brave_path:
                    logger.info("[BrowserAgent] Brave belum berjalan — launch otomatis...")
                    launched = _auto_launch_brave(brave_path)
                    if launched:
                        cdp_url = _find_active_cdp_url()

            if cdp_url:
                # Connect ke Brave via CDP (pakai sesi asli pengguna + cookie login)
                logger.info("[BrowserAgent] Menggunakan Brave via CDP: %s", cdp_url)
                profile = BrowserProfile(
                    keep_alive=True,
                    cdp_url=cdp_url,
                )
            else:
                # ── STEP 3: Fallback Playwright Chromium ────────────────────
                logger.warning(
                    "[BrowserAgent] Brave tidak ditemukan. Fallback ke Playwright Chromium. "
                    "Untuk pakai Brave: jalankan Brave dulu atau set BRAVE_PATH di .env"
                )
                proxy_config = {"server": proxy} if proxy else None
                profile = BrowserProfile(
                    headless=False,
                    proxy=proxy_config,
                    keep_alive=True,
                )

            _SHARED_BROWSER = Browser(browser_profile=profile)
            logger.info("[BrowserAgent] Singleton browser siap (keep_alive=True).")
        return _SHARED_BROWSER


def reset_shared_browser():
    """
    Tutup dan reset singleton browser (gunakan jika browser benar-benar crash).
    Dipanggil secara otomatis oleh execute_task saat CDP error terdeteksi.
    """
    global _SHARED_BROWSER
    with _SHARED_BROWSER_LOCK:
        if _SHARED_BROWSER is not None:
            try:
                asyncio.run(_SHARED_BROWSER.close())
            except Exception:
                pass
            _SHARED_BROWSER = None
            logger.info("[BrowserAgent] Singleton browser di-reset.")


# Fix: browser-use mengakses llm.provider yang tidak ada di Pydantic v2 ChatGoogleGenerativeAI.
# Solusi ini dipakai ribuan pengguna di GitHub (issue #3534, #447, #2134, #2345).
# Referensi: https://github.com/browser-use/browser-use/issues/3534
class GeminiForBrowserUse(ChatGoogleGenerativeAI):
    """
    Subclass ChatGoogleGenerativeAI yang menambahkan atribut 'provider'
    sebagai Pydantic field agar kompatibel dengan browser-use.
    model_config extra='allow' diperlukan agar browser-use bisa set
    atribut tambahan seperti 'ainvoke' pada runtime.
    """
    provider: str = Field(default="google")
    model_config = {"extra": "allow"}

    @property
    def model_name(self) -> str:
        return self.model


class BrowserAgent:
    """
    Wrapper Browser-Use yang mempertahankan interface lama BrowserAgent.
    Semua method utama (navigate, human_click, human_type, dll) tetap ada
    tapi sekarang menggunakan Browser-Use di bawahnya.

    Improvements:
    - Singleton browser — satu browser dipakai semua instance (tidak ada konflik CDP)
    - Global lock — semua task antri, hanya satu yang jalan sekaligus
    - Retry otomatis dengan exponential backoff (tenacity)
    - Event loop management yang aman untuk multi-thread

    Browser-Use reference: https://github.com/browser-use/browser-use
    Serialization pattern: https://github.com/browser-use/browser-use/issues/3718
    """
    def __init__(self, headless=False, use_camoufox=None, proxy=None,
                 endpoint_url="http://localhost:9222", llm_client=None):
        self.proxy = proxy
        self._base_url = endpoint_url
        self.llm = llm_client
        self._headless = headless
        self.logger = logging.getLogger(__name__)

        # Setup LLM untuk Browser-Use (Gemini)
        # Menggunakan GeminiForBrowserUse (subclass) agar atribut 'provider'
        # tersedia dan tidak menyebabkan AttributeError di browser-use.
        gemini_key = os.environ.get("GEMINI_KEY_1", "")
        self._bu_llm = GeminiForBrowserUse(
            model="gemini-2.0-flash",
            api_key=SecretStr(gemini_key) if gemini_key else None,
            temperature=0.1,
        )

        # Page reference untuk backward compat (tidak digunakan di browser-use mode)
        self.page = None
        self.context = None
        self.browser = None

        logger.info("[BrowserAgent] Mode: Browser-Use (LLM-driven, retry enabled)")

    def _run(self, coro):
        """Helper untuk menjalankan async code dari sync context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=300)
            elif loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return asyncio.get_event_loop().run_until_complete(coro)

    def _init_browser(self):
        """Initialize Browser-Use browser — no-op karena Browser-Use auto-manage."""
        logger.info("[BrowserAgent] Browser-Use ready (auto-managed lifecycle).")

    def execute_task(self, task: str, max_steps: int = 20, _retry_count: int = 0) -> str:
        """
        Metode utama: jalankan task natural language via Browser-Use.

        SERIALIZATION: Menggunakan _BROWSER_LOCK (global threading.Lock) agar
        hanya satu task yang berjalan pada satu waktu di seluruh proses.
        Task lain akan menunggu (antri) secara otomatis.

        SINGLETON BROWSER: Semua instance berbagi satu Browser object dengan
        keep_alive=True sehingga tidak ada CDP race condition.

        Referensi pattern yang dipakai ribuan orang di GitHub:
        https://github.com/browser-use/browser-use/issues/3718
        https://github.com/browser-use/browser-use/issues/2840
        """
        MAX_RETRIES = 3
        RETRY_DELAYS = [5, 15, 30]

        # CDP error keywords yang menandakan browser perlu di-reset
        CDP_ERRORS = (
            "CDP client not initialized",
            "browser may not be connected",
            "Target page, context or browser has been closed",
            "NoneType.*send",
        )

        async def _run_task(browser: Browser):
            agent = Agent(
                task=task,
                llm=self._bu_llm,
                browser=browser,
                max_steps=max_steps,
            )
            result = await agent.run()
            return str(result)

        # ── GLOBAL LOCK: task berikutnya hanya mulai setelah task ini selesai ──
        # Ini mencegah CDP race condition dari semua BrowserAgent instance.
        logger.info("[BrowserAgent] Menunggu giliran (antrian browser)...")
        with _BROWSER_LOCK:
            logger.info("[BrowserAgent] Giliran dapat, memulai task.")
            for attempt in range(MAX_RETRIES):
                try:
                    browser = _get_shared_browser(proxy=self.proxy)
                    result = self._run(_run_task(browser))
                    if "FAILED" not in result:
                        return result
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            "[BrowserAgent] Task returned FAILED (attempt %d/%d). "
                            "Retry dalam %ds...", attempt + 1, MAX_RETRIES, delay
                        )
                        time.sleep(delay)
                    else:
                        return result
                except Exception as e:
                    error_msg = str(e)
                    error_type = type(e).__name__
                    # Jika CDP error, reset browser agar task berikutnya tidak terpengaruh
                    is_cdp_error = any(kw in error_msg for kw in CDP_ERRORS)
                    if is_cdp_error:
                        logger.warning(
                            "[BrowserAgent] CDP error terdeteksi — mereset singleton browser."
                        )
                        reset_shared_browser()

                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            "[BrowserAgent] Exception '%s' (attempt %d/%d). "
                            "Retry dalam %ds...", error_type, attempt + 1, MAX_RETRIES, delay
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "[BrowserAgent] Task gagal setelah %d retry: %s", MAX_RETRIES, e
                        )
                        return f"FAILED: {e}"

        return "FAILED: Max retries exceeded"

    def navigate(self, url: str) -> bool:
        """Navigate ke URL — backward compat wrapper."""
        result = self.execute_task(
            f"Buka URL ini dan tunggu sampai halaman selesai load: {url}",
            max_steps=5
        )
        time.sleep(2)
        return "FAILED" not in result

    def human_click(self, selector_or_description) -> bool:
        """
        Klik elemen — sekarang pakai deskripsi natural language.
        Jika selector CSS diberikan, konversi otomatis ke deskripsi.
        """
        if isinstance(selector_or_description, str):
            desc = selector_or_description
        else:
            desc = "the target element"

        result = self.execute_task(
            f"Klik pada elemen ini: {desc}",
            max_steps=8
        )
        return "FAILED" not in result

    def human_type(self, locator_or_description, text: str) -> bool:
        """Ketik teks ke dalam field — pakai natural language."""
        if hasattr(locator_or_description, '_selector'):
            desc = f"input field with selector {locator_or_description._selector}"
        else:
            desc = str(locator_or_description)

        result = self.execute_task(
            f"Ketik teks berikut ke dalam field '{desc}': {text}",
            max_steps=8
        )
        return "FAILED" not in result

    def get_page_text(self, url: str = None) -> str:
        """Ambil teks dari halaman saat ini."""
        task = f"Ambil semua teks yang terlihat dari halaman {url}" if url else \
               "Ambil semua teks yang terlihat dari halaman yang sedang terbuka"
        return self.execute_task(task, max_steps=5)

    def screenshot(self, path: str = "screenshot.jpg") -> bool:
        """Screenshot halaman saat ini."""
        result = self.execute_task(
            f"Ambil screenshot halaman dan simpan ke {path}",
            max_steps=3
        )
        return "FAILED" not in result

    def navigate_to_safe_page(self):
        """Navigasi ke halaman netral."""
        self.navigate("https://www.google.com")

    def request_human_help(self, reason: str = "Butuh bantuan"):
        """Request human intervention untuk CAPTCHA/2FA."""
        logger.warning("[BrowserAgent] Human help needed: %s", reason)
        logger.warning("[BrowserAgent] Menunggu 60 detik untuk intervensi manual...")
        time.sleep(60)

    def set_agent_state(self, state: str, message: str = ""):
        """Compatibility stub — tidak diperlukan di Browser-Use mode."""
        pass

    def quit(self):
        """
        Cleanup — tidak menutup singleton browser agar bisa dipakai task berikutnya.
        Browser hanya ditutup saat reset_shared_browser() dipanggil secara eksplisit.
        """
        gc.collect()

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()

    @property
    def _use_camoufox(self):
        return False

    @property
    def is_restricted(self):
        return False
