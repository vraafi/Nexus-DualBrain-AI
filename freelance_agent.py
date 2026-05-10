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
            self.browser.navigate("https://www.upwork.com/ab/account-security/login")
            page.wait_for_timeout(3000)

            try:
                username_input = page.locator("input[name='login[username]'], input[type='email'], input[id='login_username']").first
                self.browser.human_type(username_input, creds["username"])
                page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
            except Exception as e:
                logging.warning(f"Could not enter username: {e}")

            try:
                password_input = page.locator("input[name='login[password]'], input[type='password'], input[id='login_password']").first
                if password_input.is_visible():
                    self.browser.human_type(password_input, creds["password"])
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(5000)
            except Exception as e:
                logging.warning(f"Could not enter password: {e}")

            if "login" in page.url or "challenge" in page.url:
                logging.warning("Manual intervention required for login (2FA/Captcha).")
                page.wait_for_timeout(15000)
                page.screenshot(path="captcha_challenge.png")
                from telegram_agent import TelegramAgent
                import os
                bot = TelegramAgent(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
                bot.send_photo("captcha_challenge.png", caption="[TINDAKAN DIPERLUKAN] AI terhenti di halaman login. Tolong selesaikan CAPTCHA atau OTP. Buka browser secara manual di komputermu, login ke Upwork dengan akun yang sama, lalu tekan ENTER di terminal ini jika sudah berhasil masuk.")
                input("\n[!!!] Buka browser aslimu, login ke Upwork untuk memecahkan CAPTCHA/OTP, lalu tekan ENTER di sini untuk melanjutkan... ")
                if "login" in page.url or "challenge" in page.url:
                    logging.error("Failed to bypass login wall.")
                    return False

            logging.info("Upwork login sequence completed.")
            return True
        except Exception as e:
            logging.error(f"Upwork login failed: {e}")
            return False

    def scrape_jobs(self):
        logging.info("Scraping Python/Web Scraping jobs from Upwork...")
        jobs = []
        try:
            page = self.browser.page
            self.browser.navigate("https://www.upwork.com/nx/search/jobs/?q=python%20automation&sort=recency")
            page.wait_for_timeout(5000)

            job_cards = page.get_by_role("article").all()
            if not job_cards:
                job_cards = page.locator("section[data-ev-label='search_results_impression'], div.job-tile").all()

            for card in job_cards[:8]:
                try:
                    title_elem = card.get_by_role("heading").first
                    if not title_elem.is_visible():
                        title_elem = card.locator("h2, h3, a.up-n-link").first
                    title = title_elem.inner_text()

                    description = card.locator("div[data-test='job-description-text'], span[data-test='job-description-text'], div.job-description").first.inner_text()

                    link_elem = card.get_by_role("link").first
                    url = link_elem.get_attribute("href")
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
        """Batch evaluate jobs using negotiation model (26b) — hemat quota dibanding 31b."""
        logging.info(f"Batch filtering {len(jobs_list)} jobs...")

        negative_keywords = ["zoom", "meeting", "hardware", "ios", "c#", "video call", "logo", "design", "photoshop"]
        candidates = []
        for job in jobs_list:
            text_to_check = (job.get('title', '') + " " + job.get('description', '')).lower()
            if not any(kw in text_to_check for kw in negative_keywords):
                candidates.append(job)

        if not candidates:
            return []

        prompt = (
            "You are an AI filtering system. Analyze the following freelance jobs. "
            "Determine if each job can be 100% completed autonomously by an AI agent "
            "restricted to writing Python code, web scraping, and API integrations. "
            "The AI CANNOT do video calls, subjective design, hardware tasks, or require "
            "personal accounts or NDA access.\n\n"
            "Respond ONLY with a JSON array: "
            "[{'index': int, 'is_autonomous': bool, 'reason': string}]\n\n"
        )

        for i, job in enumerate(candidates):
            prompt += f"Job {i}:\nTitle: {job.get('title')}\nDescription: {job.get('description')[:300]}\n---\n"

        # Gunakan negotiation model (26b) — cukup untuk filter task ini
        response = self.llm.generate_content(prompt, require_json=True, use_negotiation_model=True)
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
                            logging.info(f"LLM Approved: {candidates[idx].get('title')}")
            except Exception as e:
                logging.error(f"Failed to parse LLM filter response: {e}")

        return approved_jobs

    def submit_proposal(self, job_data, branding_context=None, script_path=None):
        logging.info(f"Submitting proposal for: {job_data.get('title')}")
        try:
            page = self.browser.page
            if job_data.get("url"):
                self.browser.navigate(job_data.get("url"))
                page.wait_for_timeout(3000)

                try:
                    apply_btn = page.get_by_role("button", name="Apply Now")
                    if not apply_btn.is_visible():
                        apply_btn = page.locator("button:has-text('Apply Now'), a:has-text('Apply Now')").first
                    self.browser.human_click(apply_btn)
                    page.wait_for_timeout(5000)
                except Exception as click_e:
                    logging.warning(f"Failed to click Apply Now: {click_e}")
                    return False

                # Generate cover letter dengan negotiation model (26b) — hemat quota
                persona = branding_context.get("persona", "Backend Python Specialist") if branding_context else "Python Automation Expert"
                prompt = (
                    f"Write a highly professional and tailored Upwork cover letter.\n"
                    f"Job Title: {job_data.get('title')}\n"
                    f"Job Description: {job_data.get('description', '')[:500]}\n\n"
                    f"My Persona: {persona}.\n"
                    "Requirements:\n"
                    "- Under 200 words\n"
                    "- Start with a specific hook about THEIR problem (not 'Hello I am a developer')\n"
                    "- Mention ONE specific technical approach\n"
                    "- End with a question that invites a reply\n"
                    "- No generic placeholders like [Your Name]"
                )

                cover_letter = self.llm.generate_content(prompt, use_negotiation_model=True)
                if not cover_letter:
                    cover_letter = (
                        f"I reviewed your requirements and can deliver a complete, tested Python solution. "
                        "What's your preferred timeline for the initial version?"
                    )

                try:
                    cover_letter_input = page.get_by_role("textbox", name="Cover Letter")
                    if not cover_letter_input.is_visible():
                        cover_letter_input = page.locator("textarea[aria-labelledby='cover_letter_label']").first

                    if cover_letter_input.is_visible():
                        self.browser.human_type(cover_letter_input, cover_letter)
                except Exception as e:
                    logging.warning(f"Failed to fill cover letter: {e}")

                try:
                    submit_btn = page.get_by_role("button", name="Send for")
                    if not submit_btn.is_visible():
                        submit_btn = page.locator("button:has-text('Send for')").first
                    self.browser.human_click(submit_btn)
                    logging.info("Proposal submitted successfully.")
                    return True
                except Exception as e:
                    logging.warning(f"Failed to click submit: {e}")
            return False
        except Exception as e:
            logging.error(f"Error submitting proposal: {e}")
            return False

    def check_messages_and_negotiate(self):
        """
        Monitor Upwork inbox, gunakan negotiation model (26b) untuk analisis & reply.
        Return: (negotiation_state, actionable_job_data)
        """
        logging.info("Checking Upwork messages for auto-negotiation...")
        negotiation_state = "NO_ACTION"
        actionable_job_data = None

        try:
            page = self.browser.page
            self.browser.navigate("https://www.upwork.com/nx/messages/")
            page.wait_for_timeout(5000)

            rooms = page.locator("div[data-test='message-room-list-item']").all()
            for room in rooms[:3]:
                try:
                    room.click()
                    page.wait_for_timeout(3000)

                    messages = page.locator("div[data-test='message-item'], div.message-content").all()
                    if not messages:
                        continue

                    chat_history = []
                    for msg in messages[-5:]:
                        chat_history.append(msg.inner_text())

                    if not chat_history:
                        continue

                    chat_text = "\n".join(chat_history)

                    # Gunakan negotiation model (26b) untuk analisis chat
                    prompt = (
                        "You are an autonomous freelance AI agent. Analyze this Upwork chat history.\n"
                        f"Chat History:\n{chat_text}\n\n"
                        "Output JSON with exactly two keys:\n"
                        "1. 'state': one of ['NO_REPLY_NEEDED', 'REPLY_ONLY', 'REVISION_REQUESTED', 'CONTRACT_ACCEPTED', 'ASK_CLARIFICATION', 'PRICE_NEGOTIATION']\n"
                        "2. 'reply_text': professional English reply (empty string if NO_REPLY_NEEDED)\n\n"
                        "For PRICE_NEGOTIATION: offer value-add before discount. Max 15% reduction.\n"
                        "For REVISION_REQUESTED: confirm scope and set timeline expectation.\n"
                        "For CONTRACT_ACCEPTED: express enthusiasm professionally, confirm start.\n"
                        "For ASK_CLARIFICATION: ask ONE specific question."
                    )

                    response = self.llm.generate_content(prompt, require_json=True, use_negotiation_model=True)
                    if response:
                        try:
                            if "```json" in response:
                                response = response.split("```json")[1].split("```")[0].strip()
                            elif "```" in response:
                                response = response.split("```")[1].strip()

                            parsed = json.loads(response)
                            state = parsed.get("state", "NO_REPLY_NEEDED")
                            reply_text = parsed.get("reply_text", "")

                            logging.info(f"Negotiation State: {state}")

                            if state != "NO_REPLY_NEEDED" and reply_text:
                                msg_input = page.locator("div[contenteditable='true'], textarea").last
                                self.browser.human_type(msg_input, reply_text)
                                self.browser.human_click("button[aria-label='Send message'], button:has-text('Send')")
                                page.wait_for_timeout(2000)

                            if state in ["REVISION_REQUESTED", "CONTRACT_ACCEPTED"]:
                                negotiation_state = state
                                room_title = page.locator("h2[data-test='room-title'], div.room-title").first.inner_text()
                                actionable_job_data = {
                                    "title": room_title,
                                    "description": f"Client follow-up based on chat:\n{chat_text}"
                                }

                        except Exception as parse_e:
                            logging.error(f"Failed to parse negotiation state: {parse_e}")

                except Exception as room_err:
                    logging.warning(f"Error handling message room: {room_err}")

        except Exception as e:
            logging.error(f"Failed to check messages: {e}")

        return negotiation_state, actionable_job_data

    def deliver_work(self, job_data, file_path):
        """Kirim deliverable ke klien via Upwork messages."""
        logging.info(f"Delivering work for: {job_data.get('title')}")
        try:
            page = self.browser.page
            self.browser.navigate("https://www.upwork.com/nx/messages/")
            page.wait_for_timeout(5000)

            try:
                room = page.locator("div[data-test='message-room-list-item']").first
                if room.is_visible():
                    self.browser.human_click("div[data-test='message-room-list-item']")
                    page.wait_for_timeout(3000)

                    file_input = page.locator("input[type='file']").first
                    if file_input:
                        file_input.set_input_files(file_path)
                        page.wait_for_timeout(2000)

                    msg_input = page.locator("div[contenteditable='true'], textarea").last

                    # Generate delivery message dengan negotiation model
                    prompt = (
                        f"Write a professional delivery message for Upwork.\n"
                        f"Job: {job_data.get('title')}\n"
                        "Requirements:\n"
                        "- Greet client by name if known\n"
                        "- Briefly explain what was built and the approach\n"
                        "- Mention that the code is tested\n"
                        "- Offer revisions if needed\n"
                        "- Under 150 words\n"
                        "- Professional but human tone"
                    )
                    delivery_msg = self.llm.generate_content(prompt, use_negotiation_model=True)
                    if not delivery_msg:
                        delivery_msg = (
                            f"Hello! I have completed the solution for '{job_data.get('title')}'. "
                            "The code is fully tested and ready to use. "
                            "Please let me know if you need any adjustments."
                        )

                    self.browser.human_type(msg_input, delivery_msg)
                    self.browser.human_click("button[aria-label='Send message'], button:has-text('Send')")
                    logging.info(f"Successfully delivered {file_path}")
                    return True
                else:
                    logging.warning("No active message rooms found.")
                    return False
            except Exception as msg_err:
                logging.error(f"Failed to navigate message UI: {msg_err}")
                return False

        except Exception as e:
            logging.error(f"Error delivering work: {e}")
            return False
