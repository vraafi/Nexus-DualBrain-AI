import logging
import time
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

class XAgent:
    """
    Agent for interacting with X (Twitter) as a sales channel.

    Fungsi utama:
    1. search_and_reply_jobs()  — cari tweet yang butuh jasa coding,
                                  reply sebagai SALES (arahkan ke payment portal).
    2. post_tech_news()         — posting tech news menarik untuk bangun audiens.

    ATURAN KERAS:
    - Semua teks yang akan diposting ke X WAJIB di-truncate ke 280 karakter.
    - Saat error, WAJIB search DuckDuckGo untuk cari solusi sebelum retry.
    - JANGAN terima order atau detail pekerjaan langsung di chat X.
    """

    def __init__(self, browser_agent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client
        self.logger = logging.getLogger(__name__)

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
        Cari solusi di DuckDuckGo saat terjadi error atau kegagalan.
        Agent WAJIB memanggil ini sebelum retry agar tidak mengulangi kesalahan yang sama.
        """
        self.logger.info("Mencari solusi di DuckDuckGo: %s", error_message[:100])
        try:
            from duckduckgo_search import DDGS
            results = DDGS().text(
                f"X Twitter Playwright automation fix: {error_message}",
                max_results=3
            )
            if not results:
                return "Tidak ada hasil pencarian."
            summary = "\n".join(r.get("body", "")[:200] for r in results)
            self.logger.info("Hasil pencarian: %s", summary[:300])
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
        """
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

            tweets = page.locator("article[data-testid='tweet']").all()
            if not tweets:
                self.logger.info("Tidak ada tweet relevan ditemukan.")
                return 0

            replied_count = 0
            for i, tweet in enumerate(tweets[:5]):
                try:
                    # Baca teks tweet
                    tweet_text = self._safe_inner_text(
                        tweet.locator("div[data-testid='tweetText']"), timeout=5000
                    )
                    if not tweet_text.strip():
                        self.logger.info("Tweet #%d: teks tidak terbaca, dilewati.", i + 1)
                        continue

                    # Evaluasi relevansi
                    eval_result = self.llm.generate_content(
                        f"Does this tweet show someone genuinely looking to hire a freelance "
                        f"Python developer or automation expert? Reply ONLY 'YES' or 'NO'.\n"
                        f"Tweet: {tweet_text}",
                        use_negotiation_model=True,
                    )
                    if "YES" not in (eval_result or "").upper():
                        self.logger.info("Tweet #%d: tidak relevan, dilewati.", i + 1)
                        continue

                    # Generate hook singkat (bukan penawaran lengkap — hanya teaser)
                    # Sisakan ruang untuk template sales + URL portal
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

                    # Susun reply final: hook + sales template
                    reply_text = (
                        f"{hook} " if hook else ""
                    ) + SALES_REPLY_TEMPLATE.format(portal=portal_url)

                    # ✅ HARD TRUNCATE — selalu enforce sebelum posting
                    reply_text = self._truncate_for_x(reply_text)

                    # Validasi panjang — jika masih terlalu panjang, gunakan template saja
                    if len(reply_text) > X_CHAR_LIMIT:
                        reply_text = self._truncate_for_x(
                            SALES_REPLY_TEMPLATE.format(portal=portal_url)
                        )

                    self.logger.info(
                        "Reply tweet #%d (%d chars): %s…",
                        i + 1, len(reply_text), reply_text[:60]
                    )

                    # Klik tombol reply
                    reply_btn = tweet.locator("button[data-testid='reply']").first
                    if not self._safe_is_visible(reply_btn):
                        self.logger.info("Tweet #%d: tombol reply tidak terlihat.", i + 1)
                        continue

                    self.browser.human_click(reply_btn)
                    page.wait_for_timeout(2000)

                    input_box = page.locator("div[data-testid='tweetTextarea_0']").first
                    if not self._safe_is_visible(input_box):
                        self.logger.warning("Tweet #%d: textarea tidak muncul.", i + 1)
                        page.keyboard.press("Escape")
                        continue

                    self.browser.human_type(input_box, reply_text)
                    page.wait_for_timeout(1000)

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
                    # ✅ Search internet untuk cari solusi sebelum lanjut ke tweet berikutnya
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
        """
        self.logger.info("Generating and posting tech news to X...")
        try:
            page = self.browser.page
            self.browser.navigate("https://x.com/home")
            page.wait_for_timeout(4000)

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
