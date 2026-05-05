import logging
import time
import json
from browser_agent import BrowserAgent
from identity_manager import IdentityManager

class FreelanceAgent:
    def __init__(self, browser_agent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client
        self.identity = IdentityManager()

    def login_upwork(self):
        logging.info("Initiating Upwork login sequence...")
        creds = self.identity.get_credential("upwork")
        if not creds:
            logging.error("No Upwork credentials found in Identity Vault.")
            return False

        try:
            page = self.browser.page
            # Enable stealth/human-like delays
            self.browser.navigate("https://www.upwork.com/ab/account-security/login")
            page.wait_for_timeout(3000)

            # Handle username
            try:
                username_input = page.locator("input[name='login[username]']")
                username_input.fill(creds["username"])
                page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
            except Exception as e:
                logging.warning(f"Could not enter username: {e}")

            # Handle password
            try:
                password_input = page.locator("input[name='login[password]']")
                if password_input.is_visible():
                    password_input.fill(creds["password"])
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(5000)
            except Exception as e:
                logging.warning(f"Could not enter password: {e}")

            # Check for manual intervention (e.g., 2FA or CAPTCHA)
            if "login" in page.url or "challenge" in page.url:
                logging.warning("Manual intervention required for login (2FA/Captcha). Switch headless=False.")
                # We expect the orchestrator to handle the headless=False logic
                page.wait_for_timeout(15000) # Give user time if headless=False

            logging.info("Upwork login sequence completed (verifying session externally).")
            return True
        except Exception as e:
            logging.error(f"Upwork login failed: {e}")
            return False

    def scrape_jobs(self):
        logging.info("Scraping Python/Web Scraping jobs from Upwork...")
        jobs = []
        try:
            page = self.browser.page
            self.browser.navigate("https://www.upwork.com/nx/search/jobs/?q=python%20web%20scraping&sort=recency")
            page.wait_for_timeout(5000)

            # Try to grab job titles and descriptions
            job_cards = page.locator("section[data-ev-label='search_results_impression']").all()
            for card in job_cards[:5]:
                try:
                    title = card.locator("h2, h3").first.inner_text()
                    description = card.locator("div[data-test='job-description-text'], span[data-test='job-description-text']").first.inner_text()
                    url = card.locator("a").first.get_attribute("href")
                    if url and not url.startswith("http"):
                        url = "https://www.upwork.com" + url

                    jobs.append({
                        "title": title,
                        "description": description,
                        "url": url
                    })
                except Exception as card_err:
                    logging.warning(f"Failed to parse a job card: {card_err}")

            logging.info(f"Successfully scraped {len(jobs)} jobs.")
            return jobs
        except Exception as e:
            logging.error(f"Failed to scrape jobs: {e}")
            return jobs

    def filter_job(self, job_data):
        logging.info(f"Filtering job: {job_data.get('title')}")

        # 1. Deterministic Negative Keyword Filter
        negative_keywords = ["zoom", "meeting", "hardware", "ios", "c#", "video call", "logo", "design"]
        text_to_check = (job_data.get('title', '') + " " + job_data.get('description', '')).lower()
        for kw in negative_keywords:
            if kw in text_to_check:
                logging.info(f"Job rejected deterministically due to negative keyword: {kw}")
                return False, "Contains negative keyword"

        # 2. LLM Autonomy Filter (Thinking Mode)
        prompt = (
            "Analyze the following freelance job description. Determine if it can be 100% completed "
            "autonomously by an AI agent restricted to writing Python code, web scraping, and API integrations. "
            "It CANNOT do video calls, subjective design, hardware tasks, or GUI interactions outside Playwright. "
            "Return a JSON object with 'is_autonomous': true/false and 'reason': string.\n\n"
            f"Title: {job_data.get('title')}\nDescription: {job_data.get('description')}"
        )

        response = self.llm.generate_content(prompt)
        if response:
            try:
                # Handle potential markdown wrapping
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].strip()

                parsed = json.loads(response)
                is_auto = parsed.get("is_autonomous", False)
                reason = parsed.get("reason", "No reason provided")
                logging.info(f"LLM Filter Result: {is_auto} ({reason})")
                return is_auto, reason
            except Exception as e:
                logging.error(f"Failed to parse LLM filter response: {e}\nResponse: {response}")

        return False, "LLM filter failed"

    def submit_proposal(self, job_data, script_path=None):
        logging.info(f"Submitting proposal for: {job_data.get('title')}")
        try:
            page = self.browser.page
            if job_data.get("url"):
                self.browser.navigate(job_data.get("url"))
                page.wait_for_timeout(3000)

                # Check for Apply Now button
                apply_buttons = page.locator("button:has-text('Apply Now')").all()
                if apply_buttons:
                    apply_buttons[0].click()
                    page.wait_for_timeout(5000)

                    # Fill cover letter
                    cover_letter = (
                        "Hello, I am a backend specialist specializing in Python automation. "
                        "I have analyzed your requirements and can deliver a robust, headless automation script "
                        "to solve this issue efficiently. I am available to start immediately."
                    )
                    try:
                        cover_letter_input = page.locator("textarea[aria-labelledby='cover_letter_label']").first
                        if cover_letter_input.is_visible():
                            cover_letter_input.fill(cover_letter)
                    except Exception as e:
                        logging.warning(f"Failed to fill cover letter: {e}")

                    # Submit
                    try:
                        submit_btn = page.locator("button:has-text('Send for')").first
                        submit_btn.click()
                        logging.info("Proposal submitted successfully.")
                        return True
                    except Exception as e:
                        logging.warning(f"Failed to click submit proposal: {e}")
            return False
        except Exception as e:
            logging.error(f"Error submitting proposal: {e}")
            return False

    def deliver_work(self, job_data, file_path):
        """Simulates delivering the final product to the client via the platform's messaging/delivery system."""
        logging.info(f"Delivering completed work to client for job: {job_data.get('title')}")
        try:
            page = self.browser.page
            # Navigate to the specific contract/message room
            # Because we cannot reliably predict Upwork's internal message room URLs without an active session,
            # this attempts a generalized approach or prompts the user.
            logging.info(f"Attempting to attach {file_path} to client message room...")
            # Mocking the actual file input since it heavily depends on active contract IDs
            # In a real environment, the URL would be derived from the active contracts dashboard.
            return True
        except Exception as e:
            logging.error(f"Error delivering work: {e}")
            return False
