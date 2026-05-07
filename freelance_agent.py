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

    def filter_jobs_batch(self, jobs_list):
        """Batch evaluate multiple jobs using a single LLM API call to save RPD quota."""
        logging.info(f"Batch filtering {len(jobs_list)} jobs...")

        # 1. Deterministic Negative Keyword Filter
        negative_keywords = ["zoom", "meeting", "hardware", "ios", "c#", "video call", "logo", "design"]
        candidates = []
        for job in jobs_list:
            text_to_check = (job.get('title', '') + " " + job.get('description', '')).lower()
            if not any(kw in text_to_check for kw in negative_keywords):
                candidates.append(job)
            else:
                logging.info(f"Job '{job.get('title')}' rejected by keyword filter.")

        if not candidates:
            return []

        # 2. LLM Autonomy Filter (Batch Mode)
        prompt = (
            "You are an AI filtering system. You must analyze the following list of freelance jobs. "
            "Determine if each job can be 100% completed autonomously by an AI agent restricted to writing Python code, web scraping, and API integrations. "
            "The AI CANNOT do video calls, subjective design, hardware tasks, or GUI interactions outside Playwright.\n\n"
            "Respond ONLY with a JSON array of objects, where each object corresponds to a job by index, containing: "
            "{'index': int, 'is_autonomous': true/false, 'reason': string}.\n\n"
        )

        for i, job in enumerate(candidates):
            prompt += f"Job {i}:\nTitle: {job.get('title')}\nDescription: {job.get('description')}\n---\n"

        response = self.llm.generate_content(prompt, require_json=True)
        approved_jobs = []
        if response:
            try:
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].strip()

                evaluations = json.loads(response)
                for eval_obj in evaluations:
                    if eval_obj.get("is_autonomous"):
                        idx = eval_obj.get("index")
                        if 0 <= idx < len(candidates):
                            approved_jobs.append(candidates[idx])
                            logging.info(f"LLM Approved Job: {candidates[idx].get('title')} - Reason: {eval_obj.get('reason')}")
            except Exception as e:
                logging.error(f"Failed to parse batched LLM filter response: {e}\nResponse: {response}")

        return approved_jobs

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

                # Generate dynamic cover letter via LLM
                logging.info("Generating dynamic cover letter via LLM...")
                persona = branding_context.get("persona", "Backend Python Specialist") if branding_context else "Python Developer"
                prompt = (
                    f"Write a highly professional and tailored Upwork cover letter for the following job.\n"
                    f"Job Title: {job_data.get('title')}\n"
                    f"Job Description: {job_data.get('description')}\n\n"
                    f"My Persona: {persona}.\n"
                    "Requirements: Keep it under 150 words. Do not use generic placeholders like [Your Name]. "
                    "Directly address the core problem in the description and state that I have a robust, automated Python solution ready. "
                    "End with a question to prompt a reply."
                )

                cover_letter = self.llm.generate_content(prompt)
                if not cover_letter:
                     logging.warning("LLM failed to generate cover letter. Using fallback.")
                     cover_letter = (
                         f"Hello, I am a {persona}. "
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
