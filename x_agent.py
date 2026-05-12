import logging
import time

class XAgent:
    """
    Agent for interacting with X (Twitter) as a fallback when Fiverr is idle.
    Functions:
    1. search_and_reply_jobs(): Search for people needing coding services and reply to them.
    2. post_tech_news(): Create an engaging/comedic tech news post to build an audience.
    """

    def __init__(self, browser_agent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client
        self.logger = logging.getLogger(__name__)

    def _safe_inner_text(self, locator, timeout=5000) -> str:
        """
        Baca inner_text dengan timeout pendek.
        Return string kosong jika elemen tidak ada atau timeout.
        """
        try:
            return locator.inner_text(timeout=timeout)
        except Exception:
            return ""

    def _safe_is_visible(self, locator, timeout=3000) -> bool:
        """
        Cek apakah elemen terlihat dengan timeout pendek.
        Return False jika timeout atau tidak ada.
        """
        try:
            return locator.is_visible(timeout=timeout)
        except Exception:
            return False

    def login_x(self):
        """Placeholder for X Login"""
        self.logger.info("Initiating X (Twitter) login sequence...")
        return True

    def search_and_reply_jobs(self):
        """
        Mencari postingan yang butuh jasa coding dan menawarkan jasa di komentar.
        """
        self.logger.info("Searching X for users needing coding services...")
        try:
            page = self.browser.page

            search_query = "looking for a developer OR need a python programmer OR hiring python -filter:links"
            search_url = f"https://x.com/search?q={search_query.replace(' ', '%20')}&src=typed_query&f=live"

            self.browser.navigate(search_url)
            page.wait_for_timeout(5000)

            tweets = page.locator("article[data-testid='tweet']").all()
            if not tweets:
                self.logger.info("No relevant tweets found needing coding services.")
                return 0

            replied_count = 0
            for i, tweet in enumerate(tweets[:5]):
                try:
                    # Baca teks dengan timeout pendek — skip jika tidak ada
                    text_locator = tweet.locator("div[data-testid='tweetText']")
                    tweet_text = self._safe_inner_text(text_locator, timeout=5000)
                    if not tweet_text.strip():
                        self.logger.info(f"Tweet #{i+1}: teks tidak terbaca, dilewati.")
                        continue

                    # Cek relevansi menggunakan LLM
                    prompt_eval = (
                        f"Does this tweet sound like someone genuinely looking to hire a freelance Python developer? "
                        f"Reply ONLY with 'YES' or 'NO'.\nTweet: {tweet_text}"
                    )
                    eval_result = self.llm.generate_content(prompt_eval, use_negotiation_model=True)
                    if "YES" not in (eval_result or "").upper():
                        self.logger.info(f"Tweet #{i+1}: tidak relevan, dilewati.")
                        continue

                    # Generate balasan profesional
                    prompt_reply = (
                        f"Write a friendly, professional, and concise reply (under 280 chars) to this tweet offering "
                        f"freelance Python development services. Do NOT include hashtags. Be conversational.\nTweet: {tweet_text}"
                    )
                    reply_text = self.llm.generate_content(prompt_reply, use_negotiation_model=True)
                    if not reply_text:
                        continue

                    # Klik tombol reply
                    reply_btn = tweet.locator("button[data-testid='reply']").first
                    if not self._safe_is_visible(reply_btn):
                        self.logger.info(f"Tweet #{i+1}: tombol reply tidak terlihat, dilewati.")
                        continue

                    self.browser.human_click(reply_btn)
                    page.wait_for_timeout(2000)

                    # Ketik balasan
                    input_box = page.locator("div[data-testid='tweetTextarea_0']").first
                    if not self._safe_is_visible(input_box):
                        self.logger.warning(f"Tweet #{i+1}: textarea tidak muncul, dilewati.")
                        page.keyboard.press("Escape")
                        continue

                    self.browser.human_type(input_box, reply_text)
                    page.wait_for_timeout(1000)

                    # Klik tombol post
                    post_btn = page.locator("button[data-testid='tweetButton']").first
                    if not self._safe_is_visible(post_btn):
                        self.logger.warning(f"Tweet #{i+1}: tombol post tidak terlihat, dilewati.")
                        page.keyboard.press("Escape")
                        continue

                    self.browser.human_click(post_btn)
                    self.logger.info(f"Replied to tweet offering services: {reply_text[:60]}...")
                    replied_count += 1
                    time.sleep(10)  # Jeda antar reply untuk hindari rate limit X

                except Exception as e:
                    self.logger.warning(f"Failed to reply to tweet #{i+1}: {e}")

            return replied_count

        except Exception as e:
            self.logger.error(f"Error in search_and_reply_jobs: {e}")
            return 0

    def post_tech_news(self):
        """
        Membuat postingan berita teknologi terbaru yang menarik dan informatif.
        """
        self.logger.info("Generating and posting tech news to X...")
        try:
            page = self.browser.page
            self.browser.navigate("https://x.com/home")
            page.wait_for_timeout(4000)

            prompt = (
                "Search for the latest technology or AI news today. Then, write a very engaging, "
                "informative, yet comedic tweet about it. It must be under 280 characters. "
                "Do not use generic hashtags, write it like a witty tech engineer."
            )
            news_tweet = self.llm.generate_content(prompt, allow_search=True)
            if not news_tweet:
                self.logger.error("Failed to generate tech news tweet.")
                return False

            news_tweet = news_tweet.strip().strip('"').strip("'")

            input_box = page.locator("div[data-testid='tweetTextarea_0']").first
            if not self._safe_is_visible(input_box):
                self.logger.warning("Tweet input box not found on home timeline.")
                return False

            self.browser.human_click(input_box)
            self.browser.human_type(input_box, news_tweet)

            post_btn = page.locator("button[data-testid='tweetButtonInline']").first
            if not self._safe_is_visible(post_btn):
                self.logger.warning("Tombol post tidak ditemukan.")
                return False

            self.browser.human_click(post_btn)
            self.logger.info(f"Successfully posted tech news: {news_tweet[:50]}...")
            return True

        except Exception as e:
            self.logger.error(f"Error posting tech news: {e}")
            return False
