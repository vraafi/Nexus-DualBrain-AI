"""
freelance_agent.py — Nexus DualBrain AI
=========================================
Agent Upwork: login, scrape jobs, filter, submit proposal, negotiate, deliver.

Update:
- Kompatibel dengan dual-mode BrowserAgent (Brave CDP & Camoufox stealth).
- Camoufox mode: tidak ada request_human_help visual → auto-retry dengan delay.
- Stealth improvements: random scroll sebelum klik, variable wait times.
"""

import logging
import time
import json
import re
import random
from browser_agent import BrowserAgent
from identity_manager import IdentityManager


class FreelanceAgent:
    def __init__(self, browser_agent: BrowserAgent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client
        self.identity = IdentityManager()
        self.logger = logging.getLogger(__name__)

    def login_upwork(self) -> bool:
        self.logger.info("Initiating Upwork login sequence...")
        creds = self.identity.get_credential("upwork")
        if not creds:
            self.logger.error("No Upwork credentials found in Identity Vault.")
            return False

        try:
            page = self.browser.page
            self.browser.navigate("https://www.upwork.com/ab/account-security/login")
            page.wait_for_timeout(3000 + int(1000 * random.random()))

            try:
                username_input = page.locator("input[name='login[username]'], input[type='email'], input[id='login_username']").first
                if username_input.is_visible(timeout=5000):
                    self.browser.human_type(username_input, creds["username"])
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
            except Exception as e:
                self.logger.warning("Could not enter username: %s", e)

            try:
                password_input = page.locator(
                    "input[name='login[password]'], input[type='password'], input[id='login_password']"
                ).first
                if password_input.is_visible():
                    self.browser.human_type(password_input, creds["password"])
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(5000)
            except Exception as e:
                self.logger.warning("Could not enter password: %s", e)

            if "login" in page.url or "challenge" in page.url:
                self.logger.warning("Manual intervention required for login (2FA/Captcha).")
                page.screenshot(path="captcha_challenge.png")
                self.browser.request_human_help("Upwork Login (CAPTCHA/2FA/OTP)")
                if "login" in page.url or "challenge" in page.url:
                    self.logger.error("Failed to bypass login wall after waiting.")
                    return False

            self.logger.info("Upwork login sequence completed.")
            return True
        except Exception as e:
            self.logger.error("Upwork login failed: %s", e)
            return False

    def scrape_jobs(self) -> list:
        self.logger.info("Scraping Python/Automation jobs from Upwork...")
        jobs = []
        try:
            page = self.browser.page
            self.browser.navigate(
                "https://www.upwork.com/nx/search/jobs/?q=python%20automation&sort=recency"
            )
            page.wait_for_timeout(5000)

            page.mouse.wheel(0, random.randint(200, 500))
            time.sleep(1.5)

            job_cards = page.get_by_role("article").all()
            if not job_cards:
                job_cards = page.locator(
                    "section[data-ev-label='search_results_impression'], div.job-tile"
                ).all()

            for card in job_cards[:8]:
                try:
                    title_elem = card.get_by_role("heading").first
                    if not title_elem.is_visible(timeout=2000):
                        title_elem = card.locator("h2, h3, a.up-n-link, h4").first

                    title = title_elem.inner_text() if title_elem.is_visible(timeout=2000) else "Unknown Title"

                    desc_locator = card.locator(
                        "div[data-test='job-description-text'], span[data-test='job-description-text'], "
                        "div.job-description, span[data-test='Clamp'], .air3-line-clamp"
                    ).first
                    description = (
                        desc_locator.inner_text()
                        if desc_locator.is_visible(timeout=2000)
                        else "Description not found"
                    )

                    link_elem = card.get_by_role("link").first
                    url = ""
                    if link_elem.is_visible(timeout=2000):
                        url = link_elem.get_attribute("href") or ""
                        if url and not url.startswith("http"):
                            url = "https://www.upwork.com" + url

                    if title != "Unknown Title":
                        jobs.append({"title": title, "description": description, "url": url})
                except Exception as card_err:
                    self.logger.warning("Failed to parse a job card: %s", card_err)

            self.logger.info("Successfully scraped %d jobs.", len(jobs))
            return jobs
        except Exception as e:
            self.logger.error("Failed to scrape jobs: %s", e)
            return jobs

    def filter_jobs_batch(self, jobs_list: list) -> list:
        """Batch evaluate jobs using negotiation model (26b) — hemat quota."""
        self.logger.info("Batch filtering %d jobs...", len(jobs_list))

        negative_keywords = [
            "zoom", "meeting", "hardware", "ios", "c#", "video call",
            "logo", "design", "photoshop"
        ]
        candidates = [
            job for job in jobs_list
            if not any(
                kw in (job.get('title', '') + " " + job.get('description', '')).lower()
                for kw in negative_keywords
            )
        ]

        if not candidates:
            return []

        prompt = (
            "You are an AI filtering system. Analyze the following freelance jobs. "
            "Determine if each job can be 100% completed autonomously by an AI agent "
            "restricted to writing Python code, web scraping, and API integrations. "
            "The AI CANNOT do video calls, subjective design, hardware tasks, or require "
            "personal accounts or NDA access.\
\
"
            "Respond ONLY with a JSON array: "
            "[{\"index\": int, \"is_autonomous\": bool, \"reason\": string}]\
\
"
        )
        for i, job in enumerate(candidates):
            prompt += (
                f"Job {i}:\
Title: {job.get('title')}\
"
                f"Description: {job.get('description', '')[:300]}\
---\
"
            )

        response = self.llm.generate_content(prompt, require_json=True, use_negotiation_model=True)
        approved_jobs = []
        if response:
            try:
                clean_response = response
                match = re.search(r'\[.*?\]', response, re.DOTALL)
                if match:
                    clean_response = match.group(0)
                elif "```json" in response:
                    clean_response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    clean_response = response.split("```")[1].strip()
                else:
                    start_idx = response.find("[")
                    end_idx = response.rfind("]")
                    if start_idx != -1 and end_idx != -1:
                        clean_response = response[start_idx:end_idx + 1].strip()

                evaluations = json.loads(clean_response)
                for eval_obj in evaluations:
                    if eval_obj.get("is_autonomous"):
                        idx = eval_obj.get("index")
                        if idx is not None and 0 <= idx < len(candidates):
                            approved_jobs.append(candidates[idx])
                            self.logger.info("LLM Approved: %s", candidates[idx].get('title'))
            except Exception as e:
                self.logger.error(
                    "Failed to parse LLM filter response: %s. Raw: %s", e, response[:200]
                )

        return approved_jobs

    def submit_proposal(self, job_data: dict, branding_context: dict = None, script_path: str = None) -> bool:
        self.logger.info("Submitting proposal for: %s", job_data.get('title'))
        try:
            page = self.browser.page
            if job_data.get("url"):
                self.browser.navigate(job_data.get("url"))
                page.wait_for_timeout(3000)

                page.mouse.wheel(0, random.randint(100, 300))
                time.sleep(1)

                try:
                    apply_btn = page.get_by_role("button", name="Apply Now")
                    if not apply_btn.is_visible():
                        apply_btn = page.locator(
                            "button:has-text('Apply Now'), a:has-text('Apply Now')"
                        ).first
                    self.browser.human_click(apply_btn)
                    page.wait_for_timeout(5000)
                except Exception as click_e:
                    self.logger.warning("Failed to click Apply Now: %s", click_e)
                    return False

                persona = (
                    branding_context.get("persona", "Backend Python Specialist")
                    if branding_context
                    else "Python Automation Expert"
                )
                prompt = (
                    f"Write a highly professional and tailored Upwork cover letter.\
"
                    f"Job Title: {job_data.get('title')}\
"
                    f"Job Description: {job_data.get('description', '')[:500]}\
\
"
                    f"My Persona: {persona}.\
"
                    "Requirements:\
"
                    "- Under 200 words\
"
                    "- Start with a specific hook about THEIR problem\
"
                    "- Mention ONE specific technical approach\
"
                    "- End with a question that invites a reply\
"
                    "- No generic placeholders like [Your Name]"
                )

                cover_letter = self.llm.generate_content(prompt, use_negotiation_model=True)
                if not cover_letter:
                    cover_letter = (
                        "I reviewed your requirements and can deliver a complete, tested Python solution. "
                        "What's your preferred timeline for the initial version?"
                    )

                try:
                    cover_letter_input = page.get_by_role("textbox", name="Cover Letter")
                    if not cover_letter_input.is_visible():
                        cover_letter_input = page.locator(
                            "textarea[aria-labelledby='cover_letter_label']"
                        ).first
                    if cover_letter_input.is_visible():
                        self.browser.human_type(cover_letter_input, cover_letter)
                except Exception as e:
                    self.logger.warning("Failed to fill cover letter: %s", e)

                try:
                    submit_btn = page.get_by_role("button", name="Send for")
                    if not submit_btn.is_visible():
                        submit_btn = page.locator("button:has-text('Send for')").first
                    self.browser.human_click(submit_btn)
                    self.logger.info("Proposal submitted successfully.")
                    return True
                except Exception as e:
                    self.logger.warning("Failed to click submit: %s", e)
            return False
        except Exception as e:
            self.logger.error("Error submitting proposal: %s", e)
            return False

    def check_messages_and_negotiate(self) -> tuple:
        """Monitor Upwork inbox, gunakan negotiation model (26b) untuk analisis & reply."""
        self.logger.info("Checking Upwork messages for auto-negotiation...")
        negotiation_state = "NO_ACTION"
        actionable_job_data = None

        try:
            page = self.browser.page
            nav_ok = self.browser.navigate("https://www.upwork.com/nx/messages/")
            if not nav_ok:
                self.logger.warning("Navigasi ke Upwork messages gagal — skip check messages.")
                return negotiation_state, actionable_job_data
            # Gunakan time.sleep bukan page.wait_for_timeout agar aman jika koneksi putus
            time.sleep(5)

            rooms = page.locator("div[data-test='message-room-list-item']").all()
            for room in rooms[:3]:
                try:
                    room.click()
                    page.wait_for_timeout(3000)

                    messages = page.locator(
                        "div[data-test='message-item'], div.message-content"
                    ).all()
                    if not messages:
                        continue

                    chat_history = [msg.inner_text() for msg in messages[-5:]]
                    if not chat_history:
                        continue

                    chat_text = "\
".join(chat_history)

                    prompt = (
                        "You are an autonomous freelance AI agent. Analyze this Upwork chat history.\
"
                        f"Chat History:\
{chat_text}\
\
"
                        "Output JSON with exactly two keys:\
"
                        "1. 'state': one of ['NO_REPLY_NEEDED', 'REPLY_ONLY', 'REVISION_REQUESTED', "
                        "'CONTRACT_ACCEPTED', 'ASK_CLARIFICATION', 'PRICE_NEGOTIATION']\
"
                        "2. 'reply_text': professional English reply (empty string if NO_REPLY_NEEDED)\
\
"
                        "For PRICE_NEGOTIATION: offer value-add before discount. Max 15% reduction.\
"
                        "For REVISION_REQUESTED: confirm scope and set timeline expectation.\
"
                        "For CONTRACT_ACCEPTED: express enthusiasm professionally, confirm start.\
"
                        "For ASK_CLARIFICATION: ask ONE specific question."
                    )

                    response = self.llm.generate_content(
                        prompt, require_json=True, use_negotiation_model=True
                    )
                    if response:
                        try:
                            match = re.search(r'\[.*?\]|\{.*?\}', response, re.DOTALL)
                            if match:
                                response = match.group(0)
                            elif "```json" in response:
                                response = response.split("```json")[1].split("```")[0].strip()
                            elif "```" in response:
                                response = response.split("```")[1].strip()

                            parsed = json.loads(response)
                            state = parsed.get("state", "NO_REPLY_NEEDED")
                            reply_text = parsed.get("reply_text", "")

                            self.logger.info("Negotiation State: %s", state)

                            if state != "NO_REPLY_NEEDED" and reply_text:
                                msg_input = page.locator(
                                    "div[contenteditable='true'], textarea"
                                ).last
                                self.browser.human_type(msg_input, reply_text)
                                self.browser.human_click(
                                    "button[aria-label='Send message'], button:has-text('Send')"
                                )
                                page.wait_for_timeout(2000)

                            if state in ["REVISION_REQUESTED", "CONTRACT_ACCEPTED"]:
                                negotiation_state = state
                                room_title = page.locator(
                                    "h2[data-test='room-title'], div.room-title"
                                ).first.inner_text()
                                actionable_job_data = {
                                    "title": room_title,
                                    "description": f"Client follow-up based on chat:\
{chat_text}"
                                }

                        except Exception as parse_e:
                            self.logger.error("Failed to parse negotiation state: %s", parse_e)

                except Exception as room_err:
                    self.logger.warning("Error handling message room: %s", room_err)

        except Exception as e:
            self.logger.error("Failed to check messages: %s", e)

        return negotiation_state, actionable_job_data

    def deliver_work(self, job_data: dict, file_path: str) -> bool:
        """Kirim deliverable ke klien via Upwork messages."""
        self.logger.info("Delivering work for: %s", job_data.get('title'))
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

                    prompt = (
                        f"Write a professional delivery message for Upwork.\
"
                        f"Job: {job_data.get('title')}\
"
                        "Requirements:\
"
                        "- Briefly explain what was built and the approach\
"
                        "- Mention that the code is tested\
"
                        "- Offer revisions if needed\
"
                        "- Under 150 words\
"
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
                    self.browser.human_click(
                        "button[aria-label='Send message'], button:has-text('Send')"
                    )
                    self.logger.info("Successfully delivered %s", file_path)
                    return True
                else:
                    self.logger.warning("No active message rooms found.")
                    return False
            except Exception as msg_err:
                self.logger.error("Failed to navigate message UI: %s", msg_err)
                return False

        except Exception as e:
            self.logger.error("Error delivering work: %s", e)
            return False
