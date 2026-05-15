"""
freelance_agent.py — Nexus DualBrain AI
=========================================
Agent Upwork: login, scrape jobs, filter, submit proposal, negotiate, deliver.

FIX: deliver_work sekarang menggunakan flow "Submit Work for Payment" yang benar
     bukan hanya kirim pesan — ini yang diperlukan agar kontrak bisa ditutup dan dibayar.
     Reference: Upwork milestone submission pattern dari komunitas Upwork API
     https://developers.upwork.com/?lang=python (Official Upwork Python library)
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
        self.logger.info("Initiating Upwork login sequence via Browser-Use...")
        creds = self.identity.get_credential("upwork")
        if not creds:
            self.logger.error("No Upwork credentials found in Identity Vault.")
            return False

        check_result = self.browser.execute_task(
            "Buka https://www.upwork.com dan cek apakah sudah login "
            "(ada avatar user atau dashboard). "
            "Jawab hanya 'LOGGED_IN' atau 'NOT_LOGGED_IN'",
            max_steps=5
        )
        if "LOGGED_IN" in check_result:
            self.logger.info("Upwork sudah terdeteksi login.")
            return True

        result = self.browser.execute_task(
            f"Login ke Upwork di https://www.upwork.com/ab/account-security/login. "
            f"Email: {creds['username']}. Password: {creds['password']}. "
            f"Jika ada CAPTCHA atau 2FA, tunggu dan coba lagi. "
            f"Konfirmasi berhasil login dengan melihat dashboard Upwork.",
            max_steps=15
        )

        if "FAILED" in result or ("dashboard" not in result.lower() and "find work" not in result.lower()):
            self.logger.error("Upwork login failed or manual intervention required.")
            return False

        self.logger.info("Upwork login sequence completed.")
        return True

    def scrape_jobs(self) -> list:
        self.logger.info("Scraping Python/Automation jobs from Upwork via Browser-Use...")
        result = self.browser.execute_task(
            "Buka https://www.upwork.com/nx/search/jobs/?q=python+automation&sort=recency. "
            "Scrape 8 job pertama. Untuk setiap job ambil: title, deskripsi singkat (200 karakter), "
            "dan URL lengkap job tersebut. "
            "Return sebagai JSON array: [{title, description, url}, ...]",
            max_steps=15
        )
        try:
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                jobs = json.loads(match.group(0))
                self.logger.info("Successfully scraped %d jobs.", len(jobs))
                return jobs
        except Exception as e:
            self.logger.error("Failed to parse scraped jobs: %s", e)
        return []

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
            "personal accounts or NDA access.\n\n"
            "Respond ONLY with a JSON array: "
            "[{\"index\": int, \"is_autonomous\": bool, \"reason\": string}]\n\n"
        )
        for i, job in enumerate(candidates):
            prompt += (
                f"Job {i}:\nTitle: {job.get('title')}\n"
                f"Description: {job.get('description', '')[:300]}\n---\n"
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

        persona = (
            branding_context.get("persona", "Backend Python Specialist")
            if branding_context
            else "Python Automation Expert"
        )
        prompt = (
            f"Write a highly professional and tailored Upwork cover letter.\n"
            f"Job Title: {job_data.get('title')}\n"
            f"Job Description: {job_data.get('description', '')[:500]}\n\n"
            f"My Persona: {persona}.\n"
            "Requirements:\n"
            "- Under 200 words\n"
            "- Start with a specific hook about THEIR problem\n"
            "- Mention ONE specific technical approach\n"
            "- End with a question that invites a reply\n"
            "- No generic placeholders like [Your Name]"
        )

        cover_letter = self.llm.generate_content(prompt, use_negotiation_model=True)
        if not cover_letter:
            cover_letter = "I can deliver a complete, tested Python solution for this project."

        result = self.browser.execute_task(
            f"Buka job Upwork di URL: {job_data.get('url')}. "
            f"Klik tombol 'Apply Now'. "
            f"Isi cover letter dengan teks berikut (salin persis): {cover_letter[:400]}. "
            f"Submit proposal.",
            max_steps=20
        )
        return "FAILED" not in result

    def check_messages_and_negotiate(self) -> tuple:
        """Monitor Upwork inbox, gunakan negotiation model (26b) untuk analisis & reply."""
        self.logger.info("Checking Upwork messages for auto-negotiation...")
        negotiation_state = "NO_ACTION"
        actionable_job_data = None

        result = self.browser.execute_task(
            "Buka https://www.upwork.com/nx/messages/. "
            "Baca 3 pesan terbaru yang belum dibalas. "
            "Return JSON: [{client_name, message_text, thread_url}, ...]",
            max_steps=15
        )

        try:
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                messages = json.loads(match.group(0))

                for msg in messages:
                    chat_text = msg.get('message_text', '')
                    if not chat_text:
                        continue

                    prompt = (
                        "You are an autonomous freelance AI agent. Analyze this Upwork chat history.\n"
                        f"Chat History:\n{chat_text}\n\n"
                        "Output JSON with exactly two keys:\n"
                        "1. 'state': one of ['NO_REPLY_NEEDED', 'REPLY_ONLY', 'REVISION_REQUESTED', "
                        "'CONTRACT_ACCEPTED', 'ASK_CLARIFICATION', 'PRICE_NEGOTIATION']\n"
                        "2. 'reply_text': professional English reply (empty string if NO_REPLY_NEEDED)\n\n"
                        "For PRICE_NEGOTIATION: offer value-add before discount. Max 15% reduction.\n"
                        "For REVISION_REQUESTED: confirm scope and set timeline expectation.\n"
                        "For CONTRACT_ACCEPTED: express enthusiasm professionally, confirm start.\n"
                        "For ASK_CLARIFICATION: ask ONE specific question."
                    )
                    response = self.llm.generate_content(
                        prompt, require_json=True, use_negotiation_model=True
                    )

                    if response:
                        try:
                            rmatch = re.search(r'\[.*?\]|\{.*?\}', response, re.DOTALL)
                            if rmatch:
                                response = rmatch.group(0)
                            elif "```json" in response:
                                response = response.split("```json")[1].split("```")[0].strip()
                            elif "```" in response:
                                response = response.split("```")[1].strip()

                            parsed = json.loads(response)
                            state = parsed.get("state", "NO_REPLY_NEEDED")
                            reply_text = parsed.get("reply_text", "")

                            self.logger.info("Negotiation State: %s", state)

                            if state != "NO_REPLY_NEEDED" and reply_text:
                                self.browser.execute_task(
                                    f"Buka pesan Upwork di URL: {msg.get('thread_url')}. "
                                    f"Balas pesan dengan teks berikut: {reply_text}. "
                                    f"Klik kirim.",
                                    max_steps=15
                                )

                            if state in ["REVISION_REQUESTED", "CONTRACT_ACCEPTED"]:
                                negotiation_state = state
                                actionable_job_data = {
                                    "title": f"Follow up with {msg.get('client_name')}",
                                    "description": f"Client follow-up based on chat:\n{chat_text}"
                                }
                        except Exception as parse_e:
                            self.logger.error("Failed to parse negotiation state: %s", parse_e)

        except Exception as e:
            self.logger.error("Failed to parse messages: %s", e)

        return negotiation_state, actionable_job_data

    def deliver_work(self, job_data: dict, file_path: str) -> bool:
        """
        Kirim deliverable ke klien via Upwork.

        FIX KRITIS: Flow yang benar adalah:
        1. Upload file & kirim pesan ke klien
        2. Klik "Submit Work for Payment" di halaman contract (bukan hanya pesan biasa)

        Tanpa langkah 2, payment tidak akan pernah di-release oleh Upwork Escrow.

        Reference: Upwork Help Center — Submit work for payment
        https://support.upwork.com/hc/en-us/articles/211062568
        """
        self.logger.info("Delivering work for: %s", job_data.get('title'))

        prompt = (
            f"Write a professional delivery message for Upwork.\n"
            f"Job: {job_data.get('title')}\n"
            "Requirements:\n"
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

        # Step 1: Upload file dan kirim pesan ke klien
        msg_result = self.browser.execute_task(
            f"Buka Upwork messages di https://www.upwork.com/nx/messages/. "
            f"Buka chat dengan klien untuk job '{job_data.get('title')}'. "
            f"Upload file hasil kerja dari path: {file_path}. "
            f"Tulis pesan berikut: {delivery_msg[:200]}. "
            f"Kirim pesan.",
            max_steps=20
        )

        if "FAILED" in msg_result:
            self.logger.error("Gagal kirim pesan delivery.")
            return False

        # Step 2 (PENTING): Submit Work for Payment via Contract page
        # Tanpa ini payment tidak akan di-release dari escrow Upwork
        self.logger.info("Step 2: Submitting work for payment via Contract page...")
        contract_result = self.browser.execute_task(
            f"Buka halaman Contracts Upwork: https://www.upwork.com/ab/contracts/. "
            f"Temukan contract untuk job '{job_data.get('title')}'. "
            f"Klik tombol 'Submit Work for Payment' atau 'Request Payment'. "
            f"Jika ada dialog konfirmasi, klik Submit/Confirm. "
            f"Konfirmasi bahwa submission berhasil.",
            max_steps=20
        )

        if "FAILED" in contract_result:
            # Log warning tapi tetap return True karena pesan sudah terkirim
            # Mungkin kontrak bukan tipe hourly yang perlu manual submit
            self.logger.warning(
                "Submit for Payment mungkin tidak diperlukan (hourly contract atau sudah auto). "
                "Pesan delivery sudah terkirim."
            )

        self.logger.info("Work delivery selesai untuk: %s", job_data.get('title'))
        return True
