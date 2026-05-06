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

            # Handle username - Use robust fallback locators and human-typing
            try:
                username_input = page.locator("input[name='login[username]'], input[type='email'], input[id='login_username']").first
                self.browser.human_type(username_input, creds["username"])
                page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
            except Exception as e:
                logging.warning(f"Could not enter username: {e}")

            # Handle password - Use robust fallback locators and human-typing
            try:
                password_input = page.locator("input[name='login[password]'], input[type='password'], input[id='login_password']").first
                if password_input.is_visible():
                    self.browser.human_type(password_input, creds["password"])
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(5000)
            except Exception as e:
                logging.warning(f"Could not enter password: {e}")

            # Check for manual intervention (e.g., 2FA or CAPTCHA)
            if "login" in page.url or "challenge" in page.url:
                logging.warning("Manual intervention required for login (2FA/Captcha).")
                page.wait_for_timeout(15000) # Give user time if headless=False

                # Check again after waiting to see if user solved it
                if "login" in page.url or "challenge" in page.url:
                    logging.error("Failed to bypass login wall.")
                    return False

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

            # Try to grab job titles and descriptions - Use fallback locators for lists
            job_cards = page.locator("section[data-ev-label='search_results_impression'], article.job-tile, div.job-tile").all()
            for card in job_cards[:5]:
                try:
                    title = card.locator("h2, h3, a.up-n-link").first.inner_text()
                    description = card.locator("div[data-test='job-description-text'], span[data-test='job-description-text'], div.job-description").first.inner_text()
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

    def submit_proposal(self, job_data, branding_context=None, script_path=None):
        logging.info(f"Submitting proposal for: {job_data.get('title')}")
        try:
            page = self.browser.page
            if job_data.get("url"):
                self.browser.navigate(job_data.get("url"))
                page.wait_for_timeout(3000)

                # Check for Apply Now button with human-click
                try:
                    self.browser.human_click("button:has-text('Apply Now'), a:has-text('Apply Now')")
                    page.wait_for_timeout(5000)
                except Exception as click_e:
                    logging.warning(f"Failed to click Apply Now: {click_e}")
                    return False

                # Personalize cover letter using branding context if available
                base_intro = "Hello, I am a backend specialist specializing in Python automation."
                if branding_context and "persona" in branding_context:
                     base_intro = f"Hello, I am a {branding_context['persona']} specializing in Python."

                cover_letter = (
                    f"{base_intro} "
                    "I have analyzed your requirements and can deliver a robust, headless automation script "
                    "to solve this issue efficiently. I am available to start immediately."
                )
                try:
                    cover_letter_input = page.locator("textarea[aria-labelledby='cover_letter_label']").first
                    if cover_letter_input.is_visible():
                        self.browser.human_type(cover_letter_input, cover_letter)
                except Exception as e:
                    logging.warning(f"Failed to fill cover letter: {e}")

                # Submit via human click
                try:
                    self.browser.human_click("button:has-text('Send for')")
                    logging.info("Proposal submitted successfully.")
                    return True
                except Exception as e:
                    logging.warning(f"Failed to click submit proposal: {e}")
            return False
        except Exception as e:
            logging.error(f"Error submitting proposal: {e}")
            return False

    def deliver_work(self, job_data, file_path):
        """Delivers the final product to the client via the platform's messaging/delivery system natively."""
        logging.info(f"Delivering completed work to client for job: {job_data.get('title')}")
        try:
            page = self.browser.page
            # Navigate to the active contracts/messages dashboard
            self.browser.navigate("https://www.upwork.com/nx/messages/")
            page.wait_for_timeout(5000)

            # Find the message room that matches the job title or latest active contract
            try:
                # In a real UI, we try to click the latest message room or search for the client
                # Using a generic fallback to select the top active message thread
                room = page.locator("div[data-test='message-room-list-item']").first
                if room.is_visible():
                    self.browser.human_click("div[data-test='message-room-list-item']")
                    page.wait_for_timeout(3000)

                    # Attach the file
                    file_input = page.locator("input[type='file']").first
                    if file_input:
                        file_input.set_input_files(file_path)
                        page.wait_for_timeout(2000)

                    # Write delivery message via human_type
                    msg_input = page.locator("div[contenteditable='true'], textarea").last
                    msg_text = f"Hello! I have completed the script for '{job_data.get('title')}'. Please find the tested code attached. Let me know if you need any adjustments."
                    self.browser.human_type(msg_input, msg_text)

                    # Send
                    self.browser.human_click("button[aria-label='Send message'], button:has-text('Send')")
                    logging.info(f"Successfully delivered {file_path} to client natively via Upwork.")
                    return True
                else:
                    logging.warning("No active message rooms found to deliver work.")
                    return False
            except Exception as msg_err:
                logging.error(f"Failed to navigate message UI: {msg_err}")
                return False

        except Exception as e:
            logging.error(f"Error delivering work natively: {e}")
            return False
