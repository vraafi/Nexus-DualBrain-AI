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

    def login_x(self):
        """Placeholder for X Login"""
        self.logger.info("Initiating X (Twitter) login sequence...")
        # To be implemented using identity_manager similar to Fiverr/Upwork
        # For now, assumes already logged in or not required for simple operations in this context
        return True

    def search_and_reply_jobs(self):
        """
        Mencari postingan yang butuh jasa coding dan menawarkan jasa di komentar.
        """
        self.logger.info("Searching X for users needing coding services...")
        try:
            page = self.browser.page

            # Use advanced search query to find people looking for devs
            search_query = "looking for a developer OR need a python programmer OR hiring python -filter:links"
            search_url = f"https://x.com/search?q={search_query.replace(' ', '%20')}&src=typed_query&f=live"

            self.browser.navigate(search_url)
            page.wait_for_timeout(5000)

            # Find tweets
            tweets = page.locator("article[data-testid='tweet']").all()
            if not tweets:
                self.logger.info("No relevant tweets found needing coding services.")
                return 0

            replied_count = 0
            for tweet in tweets[:3]:  # Limit to avoid spamming
                try:
                    tweet_text = tweet.locator("div[data-testid='tweetText']").inner_text()

                    # Cek relevansi menggunakan LLM
                    prompt_eval = (
                        f"Does this tweet sound like someone genuinely looking to hire a freelance Python developer? "
                        f"Reply ONLY with 'YES' or 'NO'.\nTweet: {tweet_text}"
                    )

                    eval_result = self.llm.generate_content(prompt_eval, use_negotiation_model=True)
                    if "YES" not in (eval_result or "").upper():
                        continue

                    # Generate balasan profesional
                    prompt_reply = (
                        f"Write a friendly, professional, and concise reply (under 280 chars) to this tweet offering "
                        f"freelance Python development services. Do NOT include hashtags. Be conversational.\nTweet: {tweet_text}"
                    )

                    reply_text = self.llm.generate_content(prompt_reply, use_negotiation_model=True)
                    if not reply_text:
                        continue

                    # Click reply button
                    reply_btn = tweet.locator("button[data-testid='reply']").first
                    if reply_btn.is_visible():
                        self.browser.human_click(reply_btn)
                        page.wait_for_timeout(2000)

                        # Type reply
                        input_box = page.locator("div[data-testid='tweetTextarea_0']").first
                        self.browser.human_type(input_box, reply_text)

                        # Click post
                        post_btn = page.locator("button[data-testid='tweetButton']").first
                        self.browser.human_click(post_btn)
                        self.logger.info(f"Replied to tweet offering services: {reply_text[:50]}...")
                        replied_count += 1
                        time.sleep(5)
                except Exception as e:
                    self.logger.warning(f"Failed to reply to a tweet: {e}")

            return replied_count
        except Exception as e:
            self.logger.error(f"Error in search_and_reply_jobs: {e}")
            return 0

    def post_tech_news(self):
        """
        Membuat postingan berita terbaru tentang teknologi dengan narasi yang menarik
        bahkan ada comedy yang informatif berdasarkan informasi terbaru.
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

            # Using Pro model to allow search and deeper reasoning
            news_tweet = self.llm.generate_content(prompt, allow_search=True)
            if not news_tweet:
                self.logger.error("Failed to generate tech news tweet.")
                return False

            # Clean up potential markdown or quotes
            news_tweet = news_tweet.strip().strip('"').strip("'")

            input_box = page.locator("div[data-testid='tweetTextarea_0']").first
            if input_box.is_visible():
                self.browser.human_click(input_box)
                self.browser.human_type(input_box, news_tweet)

                post_btn = page.locator("button[data-testid='tweetButtonInline']").first
                self.browser.human_click(post_btn)

                self.logger.info(f"Successfully posted tech news: {news_tweet[:50]}...")
                return True
            else:
                self.logger.warning("Tweet input box not found on home timeline.")
                return False
        except Exception as e:
            self.logger.error(f"Error posting tech news: {e}")
            return False
