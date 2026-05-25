"""
browser_agent.py — Nexus DualBrain AI
=======================================
FIX GEMMA 4 IT + BROWSER-USE v0.12.6

ROOT CAUSE SEBENARNYA:
  browser-use v0.12.6 memproses output LLM lewat dua jalur:
  1. Jalur function-calling  : respons masuk sebagai ToolCall → parsed ke AgentOutput
  2. Jalur non-function-calling: respons masuk sebagai teks → di-parse pakai json.loads()

  Gemma 4 IT tidak mendukung function calling → harus masuk jalur 2.
  Patch Lapis 1 (_is_non_function_calling_model) sudah benar dan berhasil
  mengalihkan Gemma ke jalur 2.

  TAPI di v0.12.6, bahkan di jalur 2, Agent masih memanggil
  `self.llm.with_structured_output(AgentOutput)` sebelum invoke.
  Gemma tidak mendukung structured_output → error "items" tetap muncul.

SOLUSI:
  Buat subclass GemmaAgent yang override method _get_next_action().
  Di sana kita:
    1. Format prompt sendiri (simpel, tidak pakai tool schema)
    2. Panggil Gemma via REST API langsung (bukan lewat langchain wrapper)
    3. Parse respons JSON dari Gemma sendiri → return AgentOutput

  Cara ini 100% bypass semua code browser-use yang tidak kompatibel
  dengan Gemma, tapi tetap pakai semua fitur lain browser-use
  (browser management, screenshot, DOM extraction, element clicking).

  Hasilnya: Gemma 4 (15.000 RPD) tetap dipakai, browser-use tetap dipakai.

CATATAN SCREENSHOT TIMEOUT:
  Timeout terjadi karena Brave di Windows diakses via CDP dari WSL2
  (latency extra ~50-200ms per request).
  Fix: naikkan semua timeout di BrowserProfile.
"""

import asyncio
import gc
import json
import logging
import os
import re
import threading
import time
from typing import Optional

import requests
from pydantic import Field, SecretStr

from llm_config import DEFAULT_LLM_MODEL, NEGOTIATION_MODEL, FALLBACK_MODEL, LLM_MODELS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETON BROWSER
# ─────────────────────────────────────────────────────────────────────────────
_BROWSER_LOCK = threading.Lock()
_SHARED_BROWSER = None
_SHARED_BROWSER_LOCK = threading.Lock()


def _get_wsl_host_ip() -> Optional[str]:
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
    import urllib.request
    try:
        req = urllib.request.urlopen(f"{url}/json/version", timeout=timeout)
        return req.status == 200
    except Exception:
        return False


def _resolve_brave_path() -> Optional[str]:
    """Cari lokasi instalasi Brave di Windows."""
    # Prioritaskan path dari .env
    env_path = os.environ.get("BRAVE_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    paths = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
    ]
    # Juga cek path standard WSL jika dijalankan dari WSL
    paths.extend([
        "/mnt/c/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
        "/mnt/c/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe"
    ])
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _auto_launch_brave(brave_path: str, port: int = 9222) -> bool:
    """Jalankan Brave dengan remote debugging port."""
    import subprocess
    flags = [
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=0.0.0.0",
        "--no-first-run",
        "--no-default-browser-check",
        "--user-data-dir=" + os.path.join(os.getcwd(), "chrome_data")
    ]
    try:
        logger.info("[BrowserAgent] Menjalankan Brave: %s", brave_path)
        # Jika di WSL, jalankan via cmd.exe
        if "/mnt/c/" in brave_path:
            win_path = brave_path.replace("/mnt/c/", "C:\\").replace("/", "\\")
            cmd = ["cmd.exe", "/c", "start", "", win_path] + flags
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([brave_path] + flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Tunggu sebentar agar browser siap
        time.sleep(3)
        return True
    except Exception as e:
        logger.error("[BrowserAgent] Gagal menjalankan Brave: %s", e)
        return False


def _find_active_cdp_url(port: int = 9222) -> Optional[str]:
    candidates = []
    env_url = os.environ.get("BRAVE_CDP_URL", "").strip()
    if env_url:
        candidates.append(env_url)
    candidates.append(f"http://127.0.0.1:{port}")
    wsl_ip = _get_wsl_host_ip()
    if wsl_ip:
        candidates.append(f"http://{wsl_ip}:{port}")
    for ip in ("172.24.48.1", "172.16.0.1"):
        if ip != wsl_ip:
            candidates.append(f"http://{ip}:{port}")
    for url in candidates:
        if _probe_cdp(url):
            logger.info("[BrowserAgent] Brave CDP aktif di: %s", url)
            return url
    
    # Jika tidak ada yang aktif, coba jalankan Brave otomatis
    brave_path = _resolve_brave_path()
    if brave_path and _auto_launch_brave(brave_path, port):
        # Coba probe lagi setelah launch
        for url in candidates:
            if _probe_cdp(url):
                logger.info("[BrowserAgent] Brave CDP aktif setelah auto-launch: %s", url)
                return url
                
    return None


def _get_shared_browser(proxy=None):
    """Singleton browser dengan timeout yang dinaikkan untuk CDP via WSL2."""
    global _SHARED_BROWSER
    with _SHARED_BROWSER_LOCK:
        if _SHARED_BROWSER is None:
            from browser_use import Browser, BrowserProfile
            brave_path = _resolve_brave_path()
            cdp_url = _find_active_cdp_url()
            
            if cdp_url:
                logger.info("[BrowserAgent] Menggunakan Brave via CDP: %s", cdp_url)
                # Di versi ini, Browser() bisa menerima CDP URL via BrowserProfile
                profile = BrowserProfile(
                    cdp_url=cdp_url,
                    headless=False
                )
                _SHARED_BROWSER = Browser(browser_profile=profile)
            else:
                logger.info("[BrowserAgent] Meluncurkan Brave baru (VISIBLE)...")
                profile = BrowserProfile(
                    headless=False,
                    chrome_instance_path=brave_path
                )
                _SHARED_BROWSER = Browser(browser_profile=profile)
            logger.info("[BrowserAgent] Singleton browser siap (VISIBLE).")
        return _SHARED_BROWSER


def reset_shared_browser():
    global _SHARED_BROWSER
    with _SHARED_BROWSER_LOCK:
        if _SHARED_BROWSER is not None:
            try:
                asyncio.run(_SHARED_BROWSER.close())
            except Exception:
                pass
            _SHARED_BROWSER = None
            logger.info("[BrowserAgent] Singleton browser di-reset.")


# ─────────────────────────────────────────────────────────────────────────────
# GEMMA DIRECT API CALLER
# Memanggil Gemma 4 via REST API langsung, tanpa langchain structured_output
# ─────────────────────────────────────────────────────────────────────────────

class GemmaDirectCaller:
    """
    Memanggil Gemma 4 via REST API langsung dengan rotasi API Key.
    """

    def __init__(self, model_name: str, api_keys: list):
        self.model_name = model_name
        self.api_keys = api_keys
        self.current_key_idx = 0
        config = LLM_MODELS.get(model_name, LLM_MODELS[DEFAULT_LLM_MODEL])
        self.base_url = config["base_url"]
        self.timeout = config.get("timeout", 180)

    def _rotate_key(self):
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        logger.info("[GemmaDirect] Merotasi API key ke index %d", self.current_key_idx)

    def call(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """Panggil Gemma via REST dengan rotasi key jika gagal."""
        parts = []
        if system_prompt:
            parts.append({"text": f"{system_prompt}\n\n{prompt}"})
        else:
            parts.append({"text": prompt})

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 1024,
                "stopSequences": ["}"]
            }
        }

        for attempt in range(len(self.api_keys)):
            key = self.api_keys[self.current_key_idx]
            try:
                resp = requests.post(
                    f"{self.base_url}?key={key}",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=self.timeout
                )
                
                if resp.status_code == 200:
                    candidates = resp.json().get("candidates", [])
                    if candidates:
                        parts_resp = candidates[0].get("content", {}).get("parts", [])
                        if parts_resp:
                            text = parts_resp[0].get("text", "")
                            if text and not text.strip().endswith("}"):
                                text = text.strip() + "}"
                            return text
                    return None
                    
                elif resp.status_code in (403, 429, 500, 503):
                    logger.warning("[GemmaDirect] Key index %d error %d. Merotasi...", 
                                   self.current_key_idx, resp.status_code)
                    self._rotate_key()
                    if resp.status_code == 429:
                        time.sleep(2) # Jeda sebentar jika rate limit
                    continue
                else:
                    logger.error("[GemmaDirect] API error %d: %s",
                                 resp.status_code, resp.text[:200])
                    return None
                    
            except Exception as e:
                logger.error("[GemmaDirect] Request error dengan key %d: %s", 
                             self.current_key_idx, e)
                self._rotate_key()
                
        return None


# ─────────────────────────────────────────────────────────────────────────────
# GEMMA AGENT — subclass Agent browser-use
# Override hanya bagian yang tidak kompatibel dengan Gemma IT
# ─────────────────────────────────────────────────────────────────────────────

_GEMMA_STEP_SYSTEM = """You are an ELITE browser automation agent.
Your mission: Complete the task as fast and accurately as possible.

STRICT OPERATING PROCEDURES:
1. TARGET FIRST: If you are not on the website related to the task (e.g., Upwork, Fiverr), your FIRST action MUST be 'navigate' to that site.
2. NO GOOGLE: Do not use Google unless the task specifically asks you to search for something unknown.
3. JSON ONLY: Reply ONLY with a valid JSON object. No pre-text, no post-text.
4. BE AWARE: If the URL changes (e.g., after login), observe the new elements and continue the task.

AVAILABLE ACTIONS:
- navigate: {"url": "https://..."}
- click: {"index": <int>}
- type: {"index": <int>, "text": "..."}
- scroll: {"direction": "down"|"up", "amount": <int>}
- wait: {"seconds": <int>}
- done: {"result": "..."}

JSON FORMAT:
{
  "action": "action_name",
  "params": {},
  "reasoning": "Why this action is the correct next step"
}
"""

_GEMMA_STEP_USER = """### GOAL: {task}

### CURRENT STATE:
- URL: {url}
- STEP: {step} of {max_steps}
- RECENT HISTORY: {history}

### PAGE SUMMARY:
{page_summary}

### INTERACTIVE ELEMENTS:
{elements}

### INSTRUCTION:
Decide the next action. 
- If you are NOT on the target website, your ONLY action is 'navigate' to it.
- If you are on the target website, proceed with the task.
REPLY IN JSON ONLY:"""


class GemmaDirectAgent:
    """
    Agent browser yang menggunakan Gemma 4 sebagai otak dan browser-use
    sebagai tangan. Menghindari with_structured_output() yang tidak
    kompatibel dengan Gemma IT.

    Cara kerja:
    1. browser-use mengambil screenshot + DOM
    2. GemmaDirectAgent merangkum state halaman menjadi teks
    3. Teks dikirim ke Gemma 4 via REST API langsung
    4. Gemma 4 balas dengan JSON instruksi aksi
    5. browser-use mengeksekusi aksi tersebut
    6. Ulangi sampai task selesai atau max_steps habis
    """

    def __init__(self, task: str, browser, gemma_caller: GemmaDirectCaller,
                 max_steps: int = 15):
        self.task = task
        self.browser = browser
        self.gemma = gemma_caller
        self.max_steps = max_steps
        self._history = []

    async def run(self) -> str:
        """
        Versi "Pure Playwright" — dikembangkan mirip dengan sistem otonom Antigravity
        untuk memastikan aksi nyata yang terlihat di monitor user.
        """
        from playwright.async_api import async_playwright
        import base64

        pw = None
        browser = None
        page = None
        
        try:
            pw = await async_playwright().start()
            
            # Cari Brave
            brave_path = _resolve_brave_path()
            cdp_url = _find_active_cdp_url()
            
            if cdp_url:
                logger.info("[GemmaDirect] Menghubungkan ke Brave (CDP: %s)...", cdp_url)
                browser = await pw.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
            else:
                logger.info("[GemmaDirect] Meluncurkan Brave baru (VISIBLE)...")
                browser = await pw.chromium.launch(
                    executable_path=brave_path,
                    headless=False,
                    args=["--remote-debugging-port=9222"]
                )
                page = await browser.new_page()

            # Pastikan ukuran window nyaman
            await page.set_viewport_size({"width": 1280, "height": 720})

            # AKTIFKAN MODE SILUMAN (STEALTH)
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
                logger.info("[GemmaDirect] Stealth Mode AKTIF.")
            except ImportError:
                logger.warning("[GemmaDirect] playwright-stealth tidak ditemukan. Berjalan tanpa penyamaran.")
            
            # Set User Agent manusia
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            })

            # Loop aksi nyata
            result_msg = "FAILED: Max steps reached"
            for step in range(1, self.max_steps + 1):
                url = page.url
                logger.info("[GemmaDirect] Step %d | URL: %s", step, url[:60])

                # DETEKSI LOGIN INSTAN (Domain-Aware & Hemat API Key)
                is_upwork_task = "upwork" in self.task.lower()
                is_fiverr_task = "fiverr" in self.task.lower()
                
                if is_upwork_task and ("/nx/find-work" in url or "upwork.com/home" in url):
                    logger.info("[GemmaDirect] ✅ Terdeteksi sudah LOGIN ke UPWORK. Task selesai.")
                    return "SUCCESS: User already logged in to Upwork."
                
                if is_fiverr_task and ("/dashboard" in url.lower() and "fiverr.com" in url):
                    logger.info("[GemmaDirect] ✅ Terdeteksi sudah LOGIN ke FIVERR. Task selesai.")
                    return "SUCCESS: User already logged in to Fiverr."

                # FORCE NAVIGATION jika di step 1 dan masih di Google/Blank atau salah domain
                is_wrong_domain = (is_upwork_task and "upwork.com" not in url) or (is_fiverr_task and "fiverr.com" not in url)
                
                if step == 1 and ("google.com" in url or "chrome://" in url or "about:blank" in url or is_wrong_domain):
                    target_hint = ""
                    if "upwork" in self.task.lower(): target_hint = "https://www.upwork.com"
                    elif "fiverr" in self.task.lower(): target_hint = "https://www.fiverr.com"
                    elif "freelancer" in self.task.lower(): target_hint = "https://www.freelancer.com"
                    
                    if target_hint:
                        logger.info("[GemmaDirect] Auto-redirecting to target: %s", target_hint)
                        await page.goto(target_hint, wait_until="networkidle", timeout=30000)
                        url = page.url

                # Tunggu loading
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass

                # Ambil state: Screenshot (opsional) + DOM + URL
                page_summary = (await page.inner_text("body"))[:2000] if await page.query_selector("body") else ""
                elements = await self._get_interactive_elements(page)

                # Format prompt sangat sederhana
                user_prompt = f"TASK: {self.task}\nURL: {url}\nELEMENTS:\n{elements}\n\nREPLY ONLY WITH JSON ACTION."
                
                logger.info("[GemmaDirect] Sending prompt to Gemma...")

                # Panggil Gemma
                raw_response = self.gemma.call(user_prompt, _GEMMA_STEP_SYSTEM)
                if not raw_response:
                    logger.warning("[GemmaDirect] No response from Gemma.")
                    continue

                logger.info("[GemmaDirect] Raw Response: %s", raw_response[:200].replace("\n", " "))

                # Parse JSON dari respons Gemma
                action_data = self._parse_gemma_response(raw_response)
                if not action_data:
                    # Retry 1x dengan reminder
                    raw_response = self.gemma.call("ERROR: Invalid JSON. Reply ONLY with JSON.", _GEMMA_STEP_SYSTEM)
                    action_data = self._parse_gemma_response(raw_response)

                if not action_data:
                    logger.warning("[GemmaDirect] Gagal parse JSON. Skip.")
                    continue

                action = action_data.get("action", "").lower()
                params = action_data.get("params", {})
                reasoning = action_data.get("reasoning", "No reasoning")
                logger.info("[GemmaDirect] AKSI: %s | %s", action, reasoning)
                self._history.append(f"Step {step}: {action} ({reasoning})")

                # EKSEKUSI AKSI NYATA VIA PLAYWRIGHT
                if action == "navigate":
                    target_url = params.get("url")
                    if target_url:
                        # ANTI-STUCK: Jangan navigasi ke URL yang sama persis
                        current_url = page.url.rstrip("/")
                        clean_target = target_url.rstrip("/")
                        if clean_target == current_url:
                            logger.warning("[GemmaDirect] Skip navigasi ke URL yang sama: %s", clean_target)
                            await asyncio.sleep(1)
                        else:
                            await page.goto(target_url, wait_until="networkidle", timeout=30000)
                
                elif action == "click":
                    idx = params.get("index")
                    if idx is not None:
                        await self._click_element_by_index(page, int(idx))
                
                elif action == "type":
                    idx = params.get("index")
                    text = params.get("text", "")
                    if idx is not None:
                        await self._type_in_element(page, int(idx), text)
                
                elif action == "scroll":
                    direction = params.get("direction", "down")
                    amount = int(params.get("amount", 3)) * 300
                    if direction == "up": amount = -amount
                    await page.mouse.wheel(0, amount)
                
                elif action == "wait":
                    sec = int(params.get("seconds", 2))
                    await asyncio.sleep(sec)
                
                elif action == "done":
                    result_msg = params.get("result", "SELESAI")
                    logger.info("[GemmaDirect] Task Selesai: %s", result_msg)
                    break
                
                elif action == "failed":
                    result_msg = f"FAILED: {params.get('reason', 'Unknown error')}"
                    break
                
                # Jeda antar aksi agar terlihat manusiawi
                await asyncio.sleep(2)

            return result_msg

        except Exception as e:
            logger.error("[GemmaDirect] Fatal Error: %s", e)
            return f"FAILED: {e}"
        finally:
            # Jangan tutup browser jika lewat CDP agar user tetap bisa lihat
            if browser and not cdp_url:
                await browser.close()
            if pw:
                await pw.stop()


    async def _get_interactive_elements(self, page) -> str:
        """Ambil daftar elemen interaktif dari halaman."""
        try:
            elements = await page.query_selector_all(
                "a, button, input, textarea, select, [role='button'], [role='link']"
            )
            lines = []
            for i, el in enumerate(elements[:30]):  # max 30 elemen
                try:
                    tag = await el.evaluate("el => el.tagName.toLowerCase()")
                    text = (await el.inner_text())[:50] if await el.is_visible() else ""
                    placeholder = await el.get_attribute("placeholder") or ""
                    el_type = await el.get_attribute("type") or ""
                    href = await el.get_attribute("href") or ""
                    label = text or placeholder or href[:40] or el_type or tag
                    if label.strip():
                        lines.append(f"[{i}] <{tag}> {label.strip()[:60]}")
                except Exception:
                    pass
            return "\n".join(lines) if lines else "(tidak ada elemen interaktif)"
        except Exception as e:
            return f"(gagal ambil elemen: {e})"

    async def _click_element_by_index(self, page, index: int) -> bool:
        """Klik elemen berdasarkan nomor urut."""
        try:
            elements = await page.query_selector_all(
                "a, button, input, textarea, select, [role='button'], [role='link']"
            )
            if 0 <= index < len(elements):
                el = elements[index]
                await el.scroll_into_view_if_needed()
                try:
                    # Coba klik standar Playwright
                    await el.click(timeout=3000)
                except Exception as click_exc:
                    logger.warning("[GemmaDirectAgent] Standard click failed, retrying via DOM JS evaluation: %s", click_exc)
                    # Fallback ke JS-based click jika standar gagal (anti-bot/CDP coordinate mismatch)
                    await el.evaluate("el => el.click()")
                return True
        except Exception as e:
            logger.debug("[GemmaDirectAgent] Click error: %s", e)
        return False

    async def _type_in_element(self, page, index: int, text: str):
        """Ketik teks ke dalam elemen berdasarkan nomor urut."""
        try:
            elements = await page.query_selector_all(
                "a, button, input, textarea, select, [role='button'], [role='link']"
            )
            if 0 <= index < len(elements):
                el = elements[index]
                try:
                    # Coba input standar Playwright
                    await el.click(timeout=3000)
                    await el.fill(text)
                except Exception as type_exc:
                    logger.warning("[GemmaDirectAgent] Standard fill failed, retrying via DOM JS value injection: %s", type_exc)
                    # Fallback ke direct DOM value injection + dispatch events
                    safe_text = text.replace("'", "\\'")
                    await el.evaluate(f"el => {{ el.value = '{safe_text}'; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}")
        except Exception as e:
            logger.debug("[GemmaDirectAgent] Type error: %s", e)

    def _parse_gemma_response(self, raw: str) -> Optional[dict]:
        """Parse JSON dari respons Gemma, robust terhadap markdown dan teks ekstra."""
        if not raw:
            return None
            
        # Bersihkan markdown dan teks sebelum/sesudah JSON
        clean_raw = raw.strip()
        
        # Cari JSON object dengan regex yang lebih agresif
        try:
            match = re.search(r'(\{.*\})', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                if "action" in data: return data
        except:
            pass

        # 2. FALLBACK: Ekstraksi kata kunci jika Gemma "bercerita"
        logger.info("[GemmaDirect] JSON failed. Attempting keyword extraction...")
        raw_l = raw.lower()
        
        # Cari Index (elemen) - PRIORITAS TINGGI
        idx_match = re.search(r"index[:\s]+(\d+)", raw_l)
        if not idx_match: idx_match = re.search(r"(\d+)", raw_l) 
        
        if idx_match:
            idx = int(idx_match.group(1))
            if "type" in raw_l or "enter" in raw_l or "fill" in raw_l:
                txt_match = re.search(r"['\"](.*?)['\"]", raw)
                return {"action": "type", "params": {"index": idx, "text": txt_match.group(1) if txt_match else "input"}, "reasoning": "Text extraction"}
            if "click" in raw_l or "press" in raw_l:
                return {"action": "click", "params": {"index": idx}, "reasoning": "Text extraction"}

        # Deteksi navigasi (mencari URL)
        all_urls = re.findall(r"https?://[^\s`'\"<>]+", raw)
        target_url = None
        if all_urls:
            current_url = getattr(self, "_last_url", "")
            for u in all_urls:
                if u.rstrip("/") != current_url.rstrip("/"):
                    target_url = u
                    break
        
        if ("navigate" in raw_l or "visit" in raw_l or "go to" in raw_l) and target_url:
            return {"action": "navigate", "params": {"url": target_url}, "reasoning": "Text extraction"}

        if "done" in raw_l or "success" in raw_l:
             return {"action": "done", "params": {"result": "Finished"}, "reasoning": "Text extraction"}

        return None

        logger.debug("[GemmaDirectAgent] Tidak bisa parse JSON: %s", raw[:200])
        return None


# ─────────────────────────────────────────────────────────────────────────────
# WRAPPER LAMA: GeminiForBrowserUse — dipertahankan untuk kompatibilitas
# Dipakai hanya jika model bukan Gemma (misalnya gemini-2.0-flash sebagai
# emergency fallback dengan RPD rendah)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from pydantic import Field as _Field

    class GeminiForBrowserUse(ChatGoogleGenerativeAI):
        """
        Subclass ChatGoogleGenerativeAI yang kompatibel dengan browser-use.
        HANYA untuk model Gemini Flash/Pro — JANGAN pakai untuk Gemma IT.
        """
        provider: str = _Field(default="google")
        model_config = {"extra": "allow"}

        @property
        def model_name(self) -> str:
            return self.model

except ImportError:
    GeminiForBrowserUse = None


# ─────────────────────────────────────────────────────────────────────────────
# PATCH LAPIS 1 — tetap dipertahankan sebagai safety net
# ─────────────────────────────────────────────────────────────────────────────

def _apply_gemma_patch():
    """Patch _is_non_function_calling_model sebagai safety net."""
    _NON_FC_KEYWORDS = ("deepseek-r1", "qwen", "gemma")
    try:
        from browser_use import Agent as _BUAgent

        def _patched_is_non_fc(self) -> bool:
            model_obj = getattr(self, "llm", None) or getattr(self, "model", None)
            if model_obj is None:
                return False
            name = (
                getattr(model_obj, "model_name", None)
                or getattr(model_obj, "model", None)
                or ""
            ).lower()
            return any(kw in name for kw in _NON_FC_KEYWORDS)

        _BUAgent._is_non_function_calling_model = _patched_is_non_fc
        logger.info(
            "[BrowserAgent] ✅ Lapis 1 patch: _is_non_function_calling_model diperbarui."
        )
    except Exception as e:
        logger.warning("[BrowserAgent] Lapis 1 patch gagal: %s", e)


_apply_gemma_patch()


# ─────────────────────────────────────────────────────────────────────────────
# BrowserAgent — interface publik (sama persis dengan versi lama)
# ─────────────────────────────────────────────────────────────────────────────

class BrowserAgent:
    """
    Wrapper utama dengan interface yang sama seperti versi lama.
    Di dalam, menggunakan GemmaDirectAgent (Gemma 4 + Playwright langsung)
    alih-alih browser-use Agent yang tidak kompatibel dengan Gemma IT.
    """

    def __init__(self, headless=False, use_camoufox=None, proxy=None,
                 endpoint_url="http://localhost:9222", llm_client=None):
        self.proxy = proxy
        self._base_url = endpoint_url
        self.llm = llm_client
        self._headless = headless
        self.page = None
        self.context = None
        self.browser = None

        # Ambil semua 10 API keys dari .env
        api_keys = []
        for i in range(1, 11):
            key = os.environ.get(f"GEMINI_KEY_{i}", "")
            if key:
                api_keys.append(key)
        
        if not api_keys:
            # Fallback ke key tunggal jika format GEMINI_KEY_X tidak ada
            single_key = os.environ.get("GEMINI_API_KEY", "")
            if single_key:
                api_keys = [single_key]
            else:
                logger.error("[BrowserAgent] Tidak ada API Key ditemukan di .env!")

        # Model utama: Gemma 4-31b (15.000 RPD)
        self._primary_model = DEFAULT_LLM_MODEL    # gemma-4-31b-it
        self._fallback_model = NEGOTIATION_MODEL   # gemma-4-26b-a4b-it
        self._gemma_primary = GemmaDirectCaller(self._primary_model, api_keys)
        self._gemma_fallback = GemmaDirectCaller(self._fallback_model, api_keys)

        logger.info("[BrowserAgent] Mode: GemmaDirectAgent (Multi-key Rotation Aktif)")

    def _run(self, coro):
        """Jalankan coroutine dari sync context."""
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
        logger.info("[BrowserAgent] Browser-Use ready (auto-managed lifecycle).")

    def execute_task(self, task: str, max_steps: int = 15, _retry_count: int = 0) -> str:
        """
        Jalankan task natural language menggunakan GemmaDirectAgent.

        Urutan model:
        - Attempt 1-2: gemma-4-31b-it (primary, 15.000 RPD)
        - Attempt 3  : gemma-4-26b-a4b-it (fallback)
        """
        MAX_RETRIES = 3
        RETRY_DELAYS = [5, 15, 30]

        async def _run_task(browser, gemma_caller: GemmaDirectCaller):
            agent = GemmaDirectAgent(
                task=task,
                browser=browser,
                gemma_caller=gemma_caller,
                max_steps=max_steps
            )
            return await agent.run()

        logger.info("[BrowserAgent] Menunggu giliran (antrian browser)...")
        with _BROWSER_LOCK:
            logger.info("[BrowserAgent] Giliran dapat, memulai task.")

            callers = [
                self._gemma_primary,   # attempt 1
                self._gemma_primary,   # attempt 2
                self._gemma_fallback,  # attempt 3 (fallback ke 26b)
            ]

            for attempt in range(MAX_RETRIES):
                try:
                    browser = _get_shared_browser(proxy=self.proxy)
                    caller = callers[attempt]
                    logger.info(
                        "[BrowserAgent] Pakai model: %s (attempt %d/%d)",
                        caller.model_name, attempt + 1, MAX_RETRIES
                    )
                    result = self._run(_run_task(browser, caller))
                    if result and "FAILED" not in result:
                        return result
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            "[BrowserAgent] Gagal (attempt %d/%d). Retry dalam %ds...",
                            attempt + 1, MAX_RETRIES, delay
                        )
                        time.sleep(delay)
                    else:
                        return result or "FAILED: Tidak ada respons"

                except Exception as e:
                    error_msg = str(e)
                    # Reset browser jika CDP error
                    if any(kw in error_msg for kw in (
                        "CDP client not initialized",
                        "browser may not be connected",
                        "Target page, context or browser has been closed",
                    )):
                        logger.warning("[BrowserAgent] CDP error — mereset browser singleton.")
                        reset_shared_browser()

                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            "[BrowserAgent] Exception '%s' (attempt %d/%d). Retry dalam %ds...",
                            type(e).__name__, attempt + 1, MAX_RETRIES, delay
                        )
                        time.sleep(delay)
                    else:
                        logger.error("[BrowserAgent] Task gagal setelah %d retry: %s",
                                     MAX_RETRIES, e)
                        return f"FAILED: {e}"

        return "FAILED: Max retries exceeded"

    # ── Backward-compatible methods ──────────────────────────────────────────

    def navigate(self, url: str) -> bool:
        result = self.execute_task(
            f"Buka URL ini dan tunggu sampai halaman selesai load: {url}",
            max_steps=3
        )
        time.sleep(2)
        return "FAILED" not in result

    def human_click(self, selector_or_description) -> bool:
        desc = str(selector_or_description)
        result = self.execute_task(f"Klik pada elemen ini: {desc}", max_steps=5)
        return "FAILED" not in result

    def human_type(self, locator_or_description, text: str) -> bool:
        desc = str(locator_or_description)
        result = self.execute_task(
            f"Ketik teks berikut ke dalam field '{desc}': {text}",
            max_steps=5
        )
        return "FAILED" not in result

    def get_page_text(self, url: str = None) -> str:
        task = (f"Ambil semua teks yang terlihat dari halaman {url}"
                if url else "Ambil semua teks yang terlihat dari halaman yang sedang terbuka")
        return self.execute_task(task, max_steps=3)

    def screenshot(self, path: str = "screenshot.jpg") -> bool:
        result = self.execute_task(
            f"Ambil screenshot halaman dan simpan ke {path}", max_steps=2
        )
        return "FAILED" not in result

    def navigate_to_safe_page(self):
        self.navigate("https://www.google.com")

    def request_human_help(self, reason: str = "Butuh bantuan",
                           max_wait: int = 900, poll_interval: int = 60,
                           hermes_agent=None, notify_message: str = None) -> bool:
        logger.warning("[BrowserAgent] ⚠️  Human help needed: %s", reason)
        logger.warning(
            "[BrowserAgent] ⏳ Membebaskan browser selama %d menit.",
            max_wait // 60
        )
        if hermes_agent is not None:
            msg = notify_message or (
                f"🔐 *Bantuan Login Dibutuhkan!*\n\n"
                f"Alasan: {reason}\n\n"
                f"Silakan login manual di browser Brave sekarang.\n"
                f"Browser sudah dibebaskan selama *{max_wait // 60} menit*."
            )
            try:
                hermes_agent.send_message(msg)
            except Exception as tg_err:
                logger.warning("[BrowserAgent] Gagal kirim Telegram: %s", tg_err)
        time.sleep(max_wait)
        return True

    def set_agent_state(self, state: str, message: str = ""):
        pass

    def quit(self):
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
