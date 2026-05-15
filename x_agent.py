import logging
import time
import random
import os

# ─────────────────────────────────────────────────────────────────────────────
# X Agent — Nexus DualBrain AI
# ─────────────────────────────────────────────────────────────────────────────
# ATURAN PENTING yang harus selalu diikuti:
#   1. Batas karakter X adalah 280 karakter (akun standar). SELALU potong/truncate
#      teks tweet SETELAH generate dari LLM — jangan percaya LLM untuk menghitung.
#   2. Saat error/gagal, SELALU cari solusi di internet via DuckDuckGo sebelum retry.
#   3. Agent ini adalah SALES BOT — tidak menerima order langsung di X.
#      SELALU arahkan calon klien ke payment portal untuk mengisi brief dan bayar.
#   4. Di X, agent memperkenalkan diri sebagai AI sales agent untuk layanan coding.
# ─────────────────────────────────────────────────────────────────────────────

PAYMENT_PORTAL_URL = os.environ.get(
    "PAYMENT_PORTAL_URL",
    "https://nexus-agent.replit.app/order"
)

X_CHAR_LIMIT = 280  # Hard limit akun standar X

# Template sales reply — mengarahkan ke payment portal, bukan terima order di chat
SALES_REPLY_TEMPLATE = (
    "Hi! I'm Nexus AI — an autonomous coding agent. "
    "I handle Python automation, web scraping & API integration. "
    "To order, fill the brief here: {portal} — I'll get started right after! "
)

# Teks-teks yang menandakan akun X sedang di-restrict
X_RESTRICTION_SIGNALS = [
    "Unlock more on X",
    "unlock more on x",
    "we want to be sure there's a human",
    "Help us learn by spending time",
    "Your content will be more discoverable",
    "Connect directly with others",
    "suspected of violating",
    "temporarily limited",
    "Account suspended",
    "account is suspended",
    "This account has been locked",
]


class XAgent:
    """
    Agent for interacting with X (Twitter) as a sales channel.

    Fungsi utama:
    1. search_and_reply_jobs()  — cari tweet yang butuh jasa coding,
                                  reply sebagai SALES (arahkan ke payment portal).
    2. post_tech_news()         — posting tech news menarik untuk bangun audiens.
    3. engage_timeline()        — mode engagement: scroll, like, tonton video.
                                  Dijalankan otomatis saat akun di-restrict.

    ATURAN KERAS:
    - Semua teks yang akan diposting ke X WAJIB di-truncate ke 280 karakter.
    - Saat error, WAJIB search DuckDuckGo untuk cari solusi sebelum retry.
    - JANGAN terima order atau detail pekerjaan langsung di chat X.
    - JIKA ada warning restriction dari X: JANGAN STOP total.
      → Otomatis masuk mode engage_timeline (scroll, like, berinteraksi)
      → Kirim notifikasi Telegram (info saja, bukan instruksi)
      → Return 'RESTRICTED' agar orchestrator pindah platform lain
    """

    def __init__(self, browser_agent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client
        self.logger = logging.getLogger(__name__)
        self._x_restricted = False  # Flag: akun sedang di-restrict oleh X
        self._restriction_notified = False  # Jangan spam Telegram

    # ─── Utility ──────────────────────────────────────────────────────────────

    def _truncate_for_x(self, text: str, limit: int = X_CHAR_LIMIT) -> str:
        """
        Potong teks agar tidak melebihi batas karakter X.
        Ini adalah safeguard KERAS — LLM sering mengabaikan instruksi karakter.
        Jika dipotong, tambahkan '…' di akhir agar terlihat natural.
        """
        if not text:
            return ""
        text = text.strip().strip('"').strip("'")
        if len(text) <= limit:
            return text
        # Potong di batas kata terdekat sebelum limit-1 (sisakan 1 char untuk …)
        truncated = text[: limit - 1]
        last_space = truncated.rfind(" ")
        if last_space > limit // 2:
            truncated = truncated[:last_space]
        self.logger.warning(
            "Tweet dipotong dari %d → %d karakter", len(text), len(truncated) + 1
        )
        return truncated + "…"

    def _search_solution(self, error_message: str) -> str:
        """
        Cari solusi di Google via Gemini saat terjadi error atau kegagalan.
        Agent WAJIB memanggil ini sebelum retry agar tidak mengulangi kesalahan yang sama.
        """
        self.logger.info("Mencari solusi di Google: %s", error_message[:100])
        try:
            # Panggil search via LLM client yang sudah mendukung Google Search
            summary = self.llm._search_web(f"Playwright automation fix for: {error_message}")
            self.logger.info("Hasil pencarian Google: %s", summary[:300])
            return summary
        except Exception as search_err:
            self.logger.error("Pencarian gagal: %s", search_err)
            return "Pencarian tidak tersedia."

    def _safe_inner_text(self, locator, timeout: int = 5000) -> str:
        try:
            return locator.inner_text(timeout=timeout)
        except Exception:
            return ""

    def _safe_is_visible(self, locator, timeout: int = 3000) -> bool:
        try:
            return locator.is_visible(timeout=timeout)
        except Exception:
            return False

    # ─── X Restriction Detection ──────────────────────────────────────────────

    @property
    def is_restricted(self) -> bool:
        """Public property agar orchestrator bisa cek status restriction."""
        return self._x_restricted

    def _check_x_restrictions(self) -> bool:
        """
        Cek apakah X menampilkan warning restriction.
        Jika terdeteksi:
          1. Set flag _x_restricted
          2. Kirim Telegram INFO (bukan instruksi — agent autonomous)
          3. Return True agar caller tahu harus switch mode

        Agent TIDAK berhenti — akan otomatis:
          - Masuk mode engage_timeline() (scroll, like, act human)
          - Orchestrator akan pindah ke platform lain (Fiverr/Upwork)
        """
        try:
            page = self.browser.page
            if not page:
                return False

            page_text = page.inner_text("body", timeout=5000)

            for signal in X_RESTRICTION_SIGNALS:
                if signal.lower() in page_text.lower():
                    self._x_restricted = True
                    self.logger.warning(
                        "⚠️ [X] Restriction terdeteksi: '%s'", signal
                    )
                    self.logger.info(
                        "🔄 [X] Beralih ke mode engagement (scroll & like) "
                        "dan pindah ke platform lain."
                    )

                    # Kirim Telegram INFO (1x saja, jangan spam)
                    if not self._restriction_notified:
                        self._restriction_notified = True
                        try:
                            import requests as req
                            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
                            if tg_token and tg_chat:
                                info_msg = (
                                    "ℹ️ INFO: Akun X terkena restriction.\n\n"
                                    f"Terdeteksi: \"{signal}\"\n\n"
                                    "Agent OTOMATIS melakukan:\n"
                                    "• Scroll timeline & like post (mode engagement)\n"
                                    "• Pindah kerja ke Fiverr/Upwork\n"
                                    "• Cek ulang restriction tiap 30 menit\n\n"
                                    "Tidak perlu intervensi manual."
                                )
                                req.post(
                                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                                    json={"chat_id": tg_chat, "text": info_msg},
                                    timeout=10
                                )
                        except Exception:
                            pass

                    return True

        except Exception as e:
            self.logger.debug("Gagal cek restriction X: %s", e)

        # Jika tidak ada signal restriction, CLEAR flag (restriction mungkin sudah dicabut)
        if self._x_restricted:
            self.logger.info("✅ [X] Restriction sepertinya sudah dicabut! Kembali ke mode normal.")
            self._x_restricted = False
            self._restriction_notified = False

        return False

    # ─── Mode Engagement (saat restricted) ────────────────────────────────────

    def engage_timeline(self, duration_seconds: int = 120) -> bool:
        """
        Mode ENGAGEMENT OTONOM — berinteraksi seperti manusia biasa.

        Dijalankan saat akun X di-restrict untuk membuktikan
        bahwa ada manusia di balik akun ini.

        Aksi yang dilakukan:
        1. Buka X home timeline
        2. Scroll perlahan (seperti baca)
        3. Like beberapa post secara acak
        4. Kadang berhenti lebih lama (seperti nonton video)
        5. TIDAK posting atau reply — hanya konsumsi konten

        Return True jika berhasil, False jika error.
        """
        self.logger.info(
            "🎯 [X] Mode engagement aktif (%ds). Scroll & like timeline...",
            duration_seconds
        )
        try:
            page = self.browser.page
            self.browser.navigate("https://x.com/home")
            page.wait_for_timeout(3000)

            start = time.time()
            likes_given = 0
            scrolls_done = 0

            while time.time() - start < duration_seconds:
                # Scroll ke bawah perlahan (simulasi baca)
                scroll_amount = random.randint(200, 600)
                page.mouse.wheel(0, scroll_amount)
                scrolls_done += 1

                # Jeda seperti manusia baca konten (3-8 detik)
                read_time = random.uniform(3, 8)
                time.sleep(read_time)

                # Kadang berhenti lebih lama (simulasi nonton video: 10-20 detik)
                if random.random() < 0.15:  # 15% chance
                    watch_time = random.uniform(10, 20)
                    self.logger.debug("[X] Menonton konten selama %.1fs...", watch_time)
                    time.sleep(watch_time)

                # Like post secara acak (tidak semua — terlihat natural)
                if random.random() < 0.3:  # 30% chance per scroll
                    try:
                        like_buttons = page.locator(
                            "button[data-testid='like']"
                        ).all()
                        if like_buttons:
                            # Pilih like button yang terlihat di viewport
                            btn = random.choice(like_buttons[-3:])  # Ambil dari post terbawah
                            if self._safe_is_visible(btn, timeout=2000):
                                self.browser.human_click(btn)
                                likes_given += 1
                                self.logger.debug(
                                    "[X] ❤️ Liked post (total: %d)", likes_given
                                )
                                time.sleep(random.uniform(1, 3))
                    except Exception:
                        pass  # Gagal like bukan masalah besar

            self.logger.info(
                "🎯 [X] Engagement selesai. Scrolls: %d, Likes: %d, Durasi: %ds",
                scrolls_done, likes_given, int(time.time() - start)
            )

            # Cek apakah restriction sudah dicabut setelah engagement
            self._check_x_restrictions()

            return True

        except Exception as e:
            self.logger.error("Error selama engagement: %s", e)
            return False

    def login_x(self):
        """Placeholder for X Login — implementasi di browser_agent."""
        self.logger.info("Initiating X (Twitter) login sequence...")
        return True

    # ─── Fungsi 1: Cari tweet & reply sebagai SALES BOT ──────────────────────

    def search_and_reply_jobs(self) -> int:
        """
        Cari tweet yang butuh jasa coding, reply sebagai sales bot.

        PENTING: Tidak menerima order di sini — hanya arahkan ke payment portal.
        Reply harus ≤ 280 karakter dan mengandung link payment portal.

        Jika restricted: otomatis jalankan engage_timeline() lalu return -1
        agar orchestrator tahu harus pindah platform.
        Return: jumlah reply (>= 0) atau -1 jika restricted.
        """
        # Jika restricted: engage dulu, lalu return -1 (sinyal ke orchestrator)
        if self._x_restricted:
            self.logger.info("[X] Akun restricted. Jalankan engagement mode...")
            self.engage_timeline(duration_seconds=90)
            return -1  # Sinyal: pindah platform

        self.logger.info("Searching X for users needing coding services...")
        try:
            page = self.browser.page
            search_query = (
                "looking for a developer OR need a python programmer OR "
                "hiring python OR need automation script -filter:links"
            )
            search_url = (
                "https://x.com/search?q="
                + search_query.replace(" ", "%20")
                + "&src=typed_query&f=live"
            )
            self.browser.navigate(search_url)
            page.wait_for_timeout(5000)

            # 🚨 CEK RESTRICTION SETELAH NAVIGASI
            if self._check_x_restrictions():
                self.logger.error("[X] Restriction terdeteksi setelah navigasi. STOP.")
                return 0

            tweets = page.locator("article[data-testid='tweet']").all()
            if not tweets:
                self.logger.info("Tidak ada tweet relevan ditemukan.")
                return 0

            replied_count = 0
            for i, tweet in enumerate(tweets[:15]):
                try:
                    # 1. Scroll via JS — tidak timeout seperti scroll_into_view_if_needed
                    try:
                        handle = tweet.element_handle(timeout=3000)
                        if handle:
                            page.evaluate("el => el.scrollIntoView({block:'center',behavior:'smooth'})", handle)
                    except Exception:
                        page.mouse.wheel(0, 400)  # fallback: scroll manual
                    time.sleep(1.5)

                    # 2. Verifikasi tweet masih valid
                    if not self._safe_is_visible(tweet, timeout=2000):
                        self.logger.debug("Tweet #%d: tidak terlihat setelah scroll, dilewati.", i + 1)
                        continue

                    # 3. CEK TOMBOL REPLY DULU SEBELUM MANGGIL LLM!
                    reply_btn = tweet.locator("button[data-testid='reply']").first
                    if not self._safe_is_visible(reply_btn, timeout=2000):
                        self.logger.debug("Tweet #%d: dilewati (tombol reply tidak terlihat/disabled).", i + 1)
                        continue

                    # 3. Baca teks tweet
                    tweet_text = self._safe_inner_text(
                        tweet.locator("div[data-testid='tweetText']"), timeout=5000
                    )
                    if not tweet_text.strip():
                        self.logger.debug("Tweet #%d: teks tidak terbaca, dilewati.", i + 1)
                        continue

                    # 4. Evaluasi relevansi dengan LLM
                    eval_result = self.llm.generate_content(
                        f"Does this tweet show someone genuinely looking to hire a freelance "
                        f"Python developer or automation expert? Reply ONLY 'YES' or 'NO'.\n"
                        f"Tweet: {tweet_text}",
                        use_negotiation_model=True,
                    )
                    if "YES" not in (eval_result or "").upper():
                        self.logger.info("Tweet #%d: tidak relevan, dilewati.", i + 1)
                        continue

                    # 5. Generate hook singkat
                    portal_url = PAYMENT_PORTAL_URL
                    template_len = len(SALES_REPLY_TEMPLATE.format(portal=portal_url))
                    hook_budget = X_CHAR_LIMIT - template_len - 5  # 5 char buffer

                    hook = ""
                    if hook_budget > 20:
                        raw_hook = self.llm.generate_content(
                            f"Write a ONE-sentence hook (max {hook_budget} chars) responding to "
                            f"this tweet, showing you understand their problem. "
                            f"Do NOT make an offer yet — just acknowledge the problem.\n"
                            f"Tweet: {tweet_text}",
                            use_negotiation_model=True,
                        ) or ""
                        hook = raw_hook.strip()[:hook_budget]

                    # 6. Susun reply final
                    reply_text = (
                        f"{hook} " if hook else ""
                    ) + SALES_REPLY_TEMPLATE.format(portal=portal_url)

                    reply_text = self._truncate_for_x(reply_text)

                    if len(reply_text) > X_CHAR_LIMIT:
                        reply_text = self._truncate_for_x(
                            SALES_REPLY_TEMPLATE.format(portal=portal_url)
                        )

                    self.logger.info(
                        "Reply tweet #%d (%d chars): %s…",
                        i + 1, len(reply_text), reply_text[:60]
                    )

                    # 7. Klik tombol reply
                    self.browser.human_click(reply_btn)
                    page.wait_for_timeout(1500)

                    # Tunggu dialog reply — coba beberapa selector (X sering ganti class)
                    REPLY_SELECTORS = [
                        "div[data-testid='tweetTextarea_0']",
                        "div[role='textbox'][aria-label*='reply' i]",
                        "div[role='textbox'][aria-label*='Post' i]",
                        "div[data-testid='tweetTextarea_0RichTextInputContainer']",
                        "div[contenteditable='true'][data-testid*='Textarea']",
                        "div[contenteditable='true'][role='textbox']",
                    ]
                    input_box = None
                    for sel in REPLY_SELECTORS:
                        try:
                            candidate = page.locator(sel).first
                            candidate.wait_for(state="visible", timeout=4000)
                            input_box = candidate
                            break
                        except Exception:
                            continue

                    if input_box is None:
                        self.logger.warning("Tweet #%d: textarea tidak ditemukan setelah coba semua selector.", i + 1)
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(1000)
                        continue

                    self.browser.human_type(input_box, reply_text)
                    page.wait_for_timeout(2000)

                    post_btn = page.locator("button[data-testid='tweetButton']").first
                    if not self._safe_is_visible(post_btn):
                        self.logger.warning("Tweet #%d: tombol post tidak terlihat.", i + 1)
                        page.keyboard.press("Escape")
                        continue

                    self.browser.human_click(post_btn)
                    replied_count += 1
                    time.sleep(10)

                except Exception as e:
                    self.logger.warning("Gagal reply tweet #%d: %s", i + 1, e)
                    self._search_solution(str(e))

            return replied_count

        except Exception as e:
            self.logger.error("Error di search_and_reply_jobs: %s", e)
            # ✅ Search internet untuk diagnosa masalah
            self._search_solution(str(e))
            return 0

    # ─── Fungsi 2: Posting tech news untuk bangun audiens ─────────────────────

    def post_tech_news(self) -> bool:
        """
        Buat dan posting tech news yang menarik untuk bangun audiens di X.

        ATURAN KERAS: Semua teks tweet WAJIB di-truncate ke 280 karakter
        sebelum diketik — LLM sering mengabaikan instruksi karakter.

        Jika restricted: otomatis engage_timeline() dan return False.
        """
        # Jika restricted: engage dulu, lalu return False
        if self._x_restricted:
            self.logger.info("[X] Akun restricted. Jalankan engagement mode...")
            self.engage_timeline(duration_seconds=60)
            return False

        self.logger.info("Generating and posting tech news to X...")
        try:
            page = self.browser.page
            self.browser.navigate("https://x.com/home")
            page.wait_for_timeout(4000)

            # Cek restriction setelah navigasi
            if self._check_x_restrictions():
                self.logger.info("[X] Restriction terdeteksi. Switch ke engagement.")
                self.engage_timeline(duration_seconds=60)
                return False

            prompt = (
                "Search for the latest technology or AI news today. "
                "Write an engaging, informative, and slightly witty tweet about it. "
                f"HARD LIMIT: The tweet MUST be under {X_CHAR_LIMIT} characters total — "
                "count carefully before responding. "
                "Do not use generic hashtags. Write like a sharp tech engineer."
            )
            raw_tweet = self.llm.generate_content(prompt, allow_search=True)
            if not raw_tweet:
                self.logger.error("LLM gagal generate tech news tweet.")
                self._search_solution("LLM returned empty response for tech news tweet")
                return False

            # ✅ HARD TRUNCATE — tidak percaya LLM untuk menghitung karakter
            news_tweet = self._truncate_for_x(raw_tweet)
            self.logger.info(
                "Tech news tweet: %d chars — '%s…'", len(news_tweet), news_tweet[:60]
            )

            input_box = page.locator("div[data-testid='tweetTextarea_0']").first
            if not self._safe_is_visible(input_box):
                self.logger.warning("Tweet input box tidak ditemukan di home timeline.")
                # ✅ Cari solusi sebelum menyerah
                self._search_solution(
                    "Playwright X.com home timeline tweetTextarea_0 not found 2025"
                )
                return False

            self.browser.human_click(input_box)
            self.browser.human_type(input_box, news_tweet)

            post_btn = page.locator("button[data-testid='tweetButtonInline']").first
            if not self._safe_is_visible(post_btn):
                self.logger.warning("Tombol post tidak ditemukan.")
                self._search_solution(
                    "Playwright X.com tweetButtonInline button not visible 2025"
                )
                return False

            self.browser.human_click(post_btn)
            self.logger.info("Tech news berhasil diposting: %s…", news_tweet[:50])
            return True

        except Exception as e:
            self.logger.error("Error posting tech news: %s", e)
            # ✅ Search internet untuk diagnosa masalah — agar tidak mengulangi kesalahan sama
            solution = self._search_solution(str(e))
            self.logger.info("Solusi dari pencarian: %s", solution[:200])
            return False
