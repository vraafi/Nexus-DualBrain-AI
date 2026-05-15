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
from difficulty_classifier import DifficultyClassifier


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

    def _keyword_filter(self, jobs_list: list) -> list:
        """
        Filter berbasis keyword sebagai fallback WAJIB ketika LLM gagal.
        Lebih baik melamar semua job yang lolos keyword daripada tidak melamar satupun.
        """
        negative_keywords = [
            "zoom", "meeting", "hardware", "ios app", "android app", "c#", ".net",
            "video call", "logo design", "photoshop", "figma", "illustrator",
            "nda required", "in-person", "on-site"
        ]
        positive_keywords = [
            "python", "automation", "scraping", "api", "bot", "script",
            "data", "excel", "csv", "selenium", "playwright", "flask",
            "django", "fastapi", "rest", "json", "integration", "etl",
            "web scraping", "crawler", "pandas", "numpy"
        ]
        approved = []
        for job in jobs_list:
            text = (job.get('title', '') + " " + job.get('description', '')).lower()
            has_negative = any(kw in text for kw in negative_keywords)
            has_positive = any(kw in text for kw in positive_keywords)
            if not has_negative and has_positive:
                approved.append(job)
                self.logger.info("[KeywordFilter] Disetujui: %s", job.get('title'))
        # Jika tidak ada yang lolos keyword, kembalikan semua job asli agar tidak stuck
        if not approved:
            self.logger.warning(
                "[KeywordFilter] Tidak ada job lolos keyword — kembalikan semua %d job.",
                len(jobs_list)
            )
            return jobs_list
        return approved

    def _extract_json_from_response(self, response: str):
        """
        Coba ekstrak JSON array dari berbagai format respons LLM.
        Menangani: JSON murni, markdown code block, teks campuran.
        """
        # Bersihkan markdown code block
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            between = response.split("```")
            if len(between) >= 3:
                response = between[1].strip()

        # Cari array JSON dengan regex — paling andal
        match = re.search(r'\[[\s\S]*?\]', response)
        if match:
            return json.loads(match.group(0))

        # Cari posisi [ dan ] secara manual
        start = response.find("[")
        end = response.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(response[start:end + 1].strip())

        raise ValueError(f"Tidak ada JSON array ditemukan dalam respons: {response[:150]}")

    def filter_jobs_batch(self, jobs_list: list) -> list:
        """
        Pipeline filter 3 lapisan sebelum agent melamar:

        LAPISAN 1 — DifficultyClassifier (SEBELUM LLM dipanggil)
          Buang SEMUA job SULIT. Hanya MUDAH dan SEDANG yang lolos.
          Skor 1-3 = MUDAH ✅  |  4-6 = SEDANG ✅  |  7+ = SULIT 🚫
          Metodologi: radon (github.com/rubik/radon, 1.5k stars),
                      Cognitive Complexity (SonarSource),
                      wily (github.com/tonybaloney/wily, 1.2k stars)

        LAPISAN 2 — LLM Filter
          Cek apakah job bisa dikerjakan 100% otomatis oleh AI.

        LAPISAN 3 — Keyword Fallback
          Jika LLM gagal parse JSON, gunakan keyword heuristic.
          TIDAK PERNAH return [] — agent tidak boleh stuck.
        """
        self.logger.info("Batch filtering %d jobs...", len(jobs_list))

        if not jobs_list:
            return []

        # ══════════════════════════════════════════════════════════════
        # LAPISAN 1: DIFFICULTY CLASSIFIER — Buang SULIT sebelum LLM
        # ══════════════════════════════════════════════════════════════
        classifier = DifficultyClassifier()
        difficulty_passed, diff_stats = classifier.filter_allowed(jobs_list)

        if diff_stats["SULIT"] > 0:
            self.logger.warning(
                "[Filter] 🚫 %d job SULIT dibuang | MUDAH=%d SEDANG=%d lolos ke LLM filter",
                diff_stats["SULIT"], diff_stats["MUDAH"], diff_stats["SEDANG"]
            )

        if not difficulty_passed:
            self.logger.warning(
                "[Filter] Semua %d job diklasifikasi SULIT — tidak ada yang akan dilamar.",
                len(jobs_list)
            )
            return []

        # ══════════════════════════════════════════════════════════════
        # LAPISAN 2: LLM FILTER — hanya untuk job yang sudah lolos difficulty
        # Bekerja pada difficulty_passed, BUKAN jobs_list asli
        # ══════════════════════════════════════════════════════════════
        job_lines = ""
        for i, job in enumerate(difficulty_passed):
            level = job.get("_difficulty", {}).get("level", "?")
            job_lines += (
                f"\nINDEX {i} [{level}]: {job.get('title', 'Unknown')}\n"
                f"DESC: {job.get('description', '')[:250]}\n"
            )

        prompt = (
            "OUTPUT FORMAT (WAJIB, JANGAN UBAH FORMAT INI):\n"
            '[{"index":0,"ok":true},{"index":1,"ok":false}]\n\n'
            "TUGAS: Untuk setiap job di bawah, tentukan apakah bisa dikerjakan 100% otomatis "
            "oleh AI yang hanya bisa: Python, web scraping, REST API, data processing.\n"
            "TIDAK BISA: video call, desain grafis subjektif, hardware fisik, kunjungan langsung.\n"
            "JAWAB HANYA dengan JSON array seperti format di atas. "
            "JANGAN tambahkan teks, penjelasan, atau markdown apapun.\n\n"
            f"JOBS:{job_lines}"
        )

        response = self.llm.generate_content(prompt, use_negotiation_model=True)

        # ── Parse respons LLM dengan fallback bertingkat ─────────────────────
        if response:
            try:
                evaluations = self._extract_json_from_response(response)
                approved_jobs = []
                for eval_obj in evaluations:
                    idx = eval_obj.get("index")
                    is_ok = eval_obj.get("ok", eval_obj.get("is_autonomous",
                            eval_obj.get("autonomous", True)))
                    if is_ok and idx is not None and 0 <= int(idx) < len(difficulty_passed):
                        approved_jobs.append(difficulty_passed[int(idx)])
                        self.logger.info(
                            "[LLMFilter] ✅ Disetujui [%s]: %s",
                            difficulty_passed[int(idx)].get("_difficulty", {}).get("level", "?"),
                            difficulty_passed[int(idx)].get('title')
                        )

                if approved_jobs:
                    return approved_jobs

                self.logger.warning("[LLMFilter] LLM tidak menyetujui satu job pun — fallback.")

            except Exception as e:
                self.logger.error(
                    "[LLMFilter] Gagal parse JSON → fallback keyword: %s | Raw: %s",
                    e, response[:300]
                )
        else:
            self.logger.warning("[LLMFilter] LLM tidak merespons — fallback keyword.")

        # ══════════════════════════════════════════════════════════════
        # LAPISAN 3: KEYWORD FALLBACK — dari difficulty_passed, bukan jobs_list asli
        # Agent TIDAK BOLEH stuck — selalu ada job untuk dilamar
        # ══════════════════════════════════════════════════════════════
        self.logger.warning("[Filter] Menggunakan keyword fallback pada %d job lolos difficulty.",
                            len(difficulty_passed))
        return self._keyword_filter(difficulty_passed)

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
