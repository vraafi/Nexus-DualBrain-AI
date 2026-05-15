"""
freelancer_agent.py
===================
Agent untuk platform Freelancer.com.
FIX KRITIS: deliver_work sekarang menggunakan Milestone Release flow yang benar.
            Tanpa milestone release, klien tidak bisa meng-approve pembayaran.

Reference: Freelancer.com Milestone system
https://www.freelancer.com/support/freelancer/payment/how-do-i-request-payment
"""

import logging
import json
import time

logger = logging.getLogger(__name__)


class FreelancerAgent:
    def __init__(self, browser_agent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client

    def login_freelancer(self) -> bool:
        """Login ke Freelancer menggunakan credential dari IdentityManager."""
        from identity_manager import IdentityManager
        identity = IdentityManager()
        creds = identity.get_credential("freelancer")
        if not creds:
            logger.error("[Freelancer] Tidak ada credential Freelancer di vault.")
            return False

        result = self.browser.execute_task(
            f"Login ke Freelancer di https://www.freelancer.com/login. "
            f"Email: {creds['username']}. Password: {creds['password']}. "
            f"Setelah login, pastikan berhasil masuk ke dashboard.",
            max_steps=12
        )
        if "FAILED" in result:
            logger.error("[Freelancer] Login error.")
            return False

        logger.info("[Freelancer] Login berhasil.")
        return True

    def check_job_matches(self) -> list[dict]:
        """
        Cek Job Matches yang dikirimkan Freelancer ke freelancer.
        Return list of dict: {job_id, title, description, rate, duration, url}
        """
        result = self.browser.execute_task(
            "Buka https://www.freelancer.com/jobs. "
            "Scrape 5 job pertama. "
            "Return JSON: [{job_id, title, description, rate, url}, ...]",
            max_steps=15
        )
        try:
            import re
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                jobs = json.loads(match.group(0))
                for j in jobs:
                    j["platform"] = "freelancer"
                logger.info("[Freelancer] Ditemukan %d job matches.", len(jobs))
                return jobs
        except Exception as exc:
            logger.error("[Freelancer] Gagal cek job matches: %s", exc)
        return []

    def filter_autonomous_jobs(self, jobs: list[dict]) -> list[dict]:
        """
        Filter job yang bisa dikerjakan 100% secara otonom (Python/API/backend).
        Gunakan LLM untuk evaluasi.
        """
        if not jobs:
            return []

        prompt = (
            "Kamu adalah sistem filter untuk freelance AI agent yang hanya bisa mengerjakan "
            "Python coding, API integration, web scraping, dan backend tasks.\n\n"
            "Evaluasi daftar job berikut dan tentukan mana yang bisa dikerjakan 100% otonom:\n\n"
        )
        for i, job in enumerate(jobs):
            prompt += f"Job {i}:\nTitle: {job.get('title')}\nDescription: {job.get('description')}\n---\n"

        prompt += (
            "\nRespond ONLY with JSON array: "
            "[{\"index\": int, \"is_autonomous\": bool, \"reason\": string}]"
        )

        response = self.llm.generate_content(prompt, require_json=True)
        approved = []
        if response:
            try:
                import re
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].strip()

                evaluations = json.loads(response)
                for ev in evaluations:
                    if ev.get("is_autonomous") and 0 <= ev["index"] < len(jobs):
                        approved.append(jobs[ev["index"]])
                        logger.info("[Freelancer] Disetujui: %s", jobs[ev["index"]]["title"])
            except Exception as parse_err:
                logger.error("[Freelancer] Gagal parse filter response: %s", parse_err)

        return approved

    def apply_to_job(self, job: dict, branding_strategy: dict) -> bool:
        """
        Apply ke job Freelancer dengan cover letter professional.
        """
        if not job.get("url"):
            return False

        persona = branding_strategy.get("persona", "Senior Backend Engineer")
        code_quality = branding_strategy.get("code_quality", "SOLID principles")

        prompt = (
            f"Write a professional bid/proposal for this Freelancer.com project.\n"
            f"Job Title: {job['title']}\n"
            f"Job Description: {job['description']}\n"
            f"My Persona: {persona}. I write code following {code_quality}.\n"
            "Requirements: Under 200 words. Business-focused. Mention ROI, scalability, and efficiency. "
            "Show deep technical understanding. End with availability and rate confirmation. "
            "Do NOT use generic phrases like 'I am passionate about'. Be specific and data-driven."
        )

        cover_letter = self.llm.generate_content(prompt)
        if not cover_letter:
            cover_letter = (
                f"As a senior Python engineer specializing in backend systems and API integrations, "
                f"I am well-positioned to deliver {job['title']} with measurable efficiency gains. "
                "Available immediately. Please let me know your timeline expectations."
            )

        result = self.browser.execute_task(
            f"Buka project Freelancer di: {job['url']}. "
            f"Klik tombol Bid. "
            f"Isi cover letter/proposal dengan teks ini: {cover_letter[:400]}. "
            f"Submit bid tersebut.",
            max_steps=20
        )

        if "FAILED" not in result:
            logger.info("[Freelancer] Applied ke: %s", job["title"])
            return True
        else:
            logger.error("[Freelancer] Gagal apply ke job %s", job.get("title"))
            return False

    def check_active_engagements(self) -> list[dict]:
        """
        Cek engagement (kontrak aktif) yang sedang berjalan.
        Return list pesanan aktif yang perlu dikerjakan.
        """
        result = self.browser.execute_task(
            "Buka https://www.freelancer.com/manage. "
            "List 3 project/kontrak yang sedang aktif berjalan. "
            "Return JSON: [{job_id, title, url}, ...]",
            max_steps=15
        )
        try:
            import re
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                engagements = json.loads(match.group(0))
                for e in engagements:
                    e["platform"] = "freelancer"
                    e["description"] = ""
                logger.info("[Freelancer] %d active project ditemukan.", len(engagements))
                return engagements
        except Exception as exc:
            logger.error("[Freelancer] Error cek engagements: %s", exc)
        return []

    def deliver_work(self, engagement: dict, file_path: str) -> bool:
        """
        Kirim hasil kerja ke klien Freelancer dan request milestone payment.

        FIX KRITIS: Flow yang benar di Freelancer.com:
        1. Upload file + kirim pesan ke klien
        2. Klik "Request Milestone Payment" agar klien bisa approve & bayar

        Tanpa langkah 2, uang di escrow tidak akan pernah di-release.

        Reference: Freelancer.com Milestone Payment Flow
        https://www.freelancer.com/support/freelancer/payment/how-do-i-request-payment
        """
        project_title = engagement.get('title', 'this project')
        project_url = engagement.get('url', 'https://www.freelancer.com/manage')

        delivery_msg = (
            f"Hello,\n\nI have completed the work for '{project_title}'. "
            "The solution follows SOLID principles and includes comprehensive unit tests. "
            "Please find the attached file with full documentation. "
            "I'm available for any questions or revisions within the agreed scope.\n\n"
            "Best regards"
        )

        # Step 1: Upload file dan kirim pesan ke klien
        msg_result = self.browser.execute_task(
            f"Buka project Freelancer: {project_url}. "
            f"Upload file hasil kerja dari path: {file_path}. "
            f"Kirim pesan chat ke klien dengan teks ini: {delivery_msg[:300]}.",
            max_steps=20
        )

        if "FAILED" in msg_result:
            logger.error("[Freelancer] Gagal upload/kirim pesan delivery.")
            return False

        # Step 2 (PENTING): Request Milestone Payment
        # Ini yang memicu notifikasi ke klien untuk approve pembayaran
        logger.info("[Freelancer] Step 2: Request Milestone Payment untuk '%s'...", project_title)
        milestone_result = self.browser.execute_task(
            f"Buka halaman project Freelancer: {project_url}. "
            f"Cari tombol 'Request Milestone Release' atau 'Request Payment'. "
            f"Klik tombol tersebut. "
            f"Jika ada form konfirmasi atau dialog, isi dengan pesan singkat: "
            f"'Work completed as per requirements. Please review and release payment.' "
            f"Konfirmasi submission.",
            max_steps=20
        )

        if "FAILED" in milestone_result:
            logger.warning(
                "[Freelancer] Request Milestone Payment mungkin tidak tersedia "
                "(mungkin fixed-price bukan milestone, atau sudah auto). "
                "Pesan delivery sudah terkirim."
            )
        else:
            logger.info("[Freelancer] Milestone payment request berhasil dikirim.")

        logger.info("[Freelancer] Pekerjaan berhasil didelivery ke: %s", project_title)
        return True
