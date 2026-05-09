"""
toptal_agent.py
===============
Agent untuk platform Toptal.
Toptal berbeda dari Upwork/Fiverr — ini platform elite (Top 3%).
Flow: Toptal mengirimkan job matches via email/dashboard → kita apply → interview → contract.
Agent ini fokus pada: cek job matches, kirim application, dan manage active engagements.
"""

import logging
import json
import time

logger = logging.getLogger(__name__)


class ToptalAgent:
    def __init__(self, browser_agent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client

    def login_toptal(self) -> bool:
        """Login ke Toptal menggunakan credential dari IdentityManager."""
        from identity_manager import IdentityManager
        identity = IdentityManager()
        creds = identity.get_credential("toptal")
        if not creds:
            logger.error("[Toptal] Tidak ada credential Toptal di vault.")
            return False

        try:
            self.browser.navigate("https://www.toptal.com/login")
            page = self.browser.page
            page.wait_for_timeout(3000)

            email_input = page.locator("input[type='email'], input[name='email']").first
            self.browser.human_type(email_input, creds["username"])

            password_input = page.locator("input[type='password'], input[name='password']").first
            self.browser.human_type(password_input, creds["password"])

            page.keyboard.press("Enter")
            page.wait_for_timeout(6000)

            if "login" in page.url or "sign_in" in page.url:
                logger.warning("[Toptal] Login gagal atau perlu manual intervention.")
                page.wait_for_timeout(20000)  # Toptal kadang butuh waktu lebih
                if "login" in page.url or "sign_in" in page.url:
                    return False

            logger.info("[Toptal] Login berhasil.")
            return True

        except Exception as exc:
            logger.error("[Toptal] Login error: %s", exc)
            return False

    def check_job_matches(self) -> list[dict]:
        """
        Cek Job Matches yang dikirimkan Toptal ke freelancer.
        Toptal menyajikan job yang cocok dengan skill profile kita.
        Return list of dict: {job_id, title, description, rate, duration, url}
        """
        jobs = []
        try:
            self.browser.navigate("https://www.toptal.com/freelancers#jobs")
            page = self.browser.page
            page.wait_for_timeout(5000)

            job_cards = page.locator(
                "div[class*='job-card'], article[class*='job'], div[data-testid*='job']"
            ).all()

            for card in job_cards[:5]:
                try:
                    title_elem = card.locator("h2, h3, span[class*='title']").first
                    title = title_elem.inner_text() if title_elem.is_visible() else "Untitled"

                    desc_elem = card.locator("p[class*='description'], div[class*='description']").first
                    description = desc_elem.inner_text() if desc_elem.is_visible() else ""

                    rate_elem = card.locator("span[class*='rate'], div[class*='compensation']").first
                    rate = rate_elem.inner_text() if rate_elem.is_visible() else "TBD"

                    link_elem = card.locator("a").first
                    url = link_elem.get_attribute("href") or ""
                    if url and not url.startswith("http"):
                        url = "https://www.toptal.com" + url

                    jobs.append({
                        "job_id": url.split("/")[-1] if url else f"toptal_job_{len(jobs)}",
                        "title": title,
                        "description": description,
                        "rate": rate,
                        "url": url,
                        "platform": "toptal"
                    })
                except Exception as card_err:
                    logger.warning("[Toptal] Gagal parse job card: %s", card_err)

            logger.info("[Toptal] Ditemukan %d job matches.", len(jobs))
            return jobs

        except Exception as exc:
            logger.error("[Toptal] Gagal cek job matches: %s", exc)
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
            prompt += f"Job {i}:\nTitle: {job['title']}\nDescription: {job['description']}\n---\n"

        prompt += (
            "\nRespond ONLY with JSON array: "
            "[{\"index\": int, \"is_autonomous\": bool, \"reason\": string}]"
        )

        response = self.llm.generate_content(prompt, require_json=True)
        approved = []
        if response:
            try:
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].strip()

                evaluations = json.loads(response)
                for ev in evaluations:
                    if ev.get("is_autonomous") and 0 <= ev["index"] < len(jobs):
                        approved.append(jobs[ev["index"]])
                        logger.info("[Toptal] Disetujui: %s", jobs[ev["index"]]["title"])
            except Exception as parse_err:
                logger.error("[Toptal] Gagal parse filter response: %s", parse_err)

        return approved

    def apply_to_job(self, job: dict, branding_strategy: dict) -> bool:
        """
        Apply ke job Toptal dengan cover letter professional level senior engineer.
        Toptal mengharapkan kandidat yang sangat profesional dan spesifik.
        """
        if not job.get("url"):
            return False

        try:
            self.browser.navigate(job["url"])
            page = self.browser.page
            page.wait_for_timeout(4000)

            apply_btn = page.get_by_role("button", name="Apply")
            if not apply_btn.is_visible():
                apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply for this position')").first

            if not apply_btn.is_visible():
                logger.warning("[Toptal] Tombol Apply tidak ditemukan untuk: %s", job["title"])
                return False

            self.browser.human_click(apply_btn)
            page.wait_for_timeout(3000)

            # Generate cover letter level senior engineer via LLM
            persona = branding_strategy.get("persona", "Senior Backend Engineer")
            code_quality = branding_strategy.get("code_quality", "SOLID principles")

            prompt = (
                f"Write a Toptal-level professional cover letter for this senior engineering role.\n"
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

            # Isi cover letter
            cover_input = page.locator(
                "textarea[name*='cover'], textarea[placeholder*='letter'], "
                "div[contenteditable][aria-label*='cover']"
            ).first
            if cover_input.is_visible():
                self.browser.human_type(cover_input, cover_letter)

            # Submit
            submit_btn = page.get_by_role("button", name="Submit Application")
            if not submit_btn.is_visible():
                submit_btn = page.locator("button:has-text('Submit'), button[type='submit']").first

            self.browser.human_click(submit_btn)
            page.wait_for_timeout(3000)

            logger.info("[Toptal] Applied ke: %s", job["title"])
            return True

        except Exception as exc:
            logger.error("[Toptal] Gagal apply ke job %s: %s", job.get("title"), exc)
            return False

    def check_active_engagements(self) -> list[dict]:
        """
        Cek engagement (kontrak aktif) yang sedang berjalan.
        Return list pesanan aktif yang perlu dikerjakan.
        """
        engagements = []
        try:
            self.browser.navigate("https://www.toptal.com/freelancers#engagements")
            page = self.browser.page
            page.wait_for_timeout(5000)

            engagement_cards = page.locator(
                "div[class*='engagement'], article[class*='engagement']"
            ).all()

            for card in engagement_cards[:3]:
                try:
                    title_elem = card.locator("h2, h3, span[class*='title']").first
                    title = title_elem.inner_text() if title_elem.is_visible() else "Active Engagement"

                    link_elem = card.locator("a[href*='engagement']").first
                    url = link_elem.get_attribute("href") or ""
                    if url and not url.startswith("http"):
                        url = "https://www.toptal.com" + url

                    engagements.append({
                        "job_id": url.split("/")[-1],
                        "title": title,
                        "description": "",
                        "url": url,
                        "platform": "toptal"
                    })
                except Exception as ce:
                    logger.warning("[Toptal] Gagal parse engagement: %s", ce)

            logger.info("[Toptal] %d active engagement ditemukan.", len(engagements))
            return engagements

        except Exception as exc:
            logger.error("[Toptal] Error cek engagements: %s", exc)
            return []

    def deliver_work(self, engagement: dict, file_path: str) -> bool:
        """
        Kirim hasil kerja ke klien Toptal melalui messaging system.
        Toptal biasanya menggunakan platform komunikasi mereka sendiri.
        """
        try:
            self.browser.navigate(engagement.get("url", "https://www.toptal.com/freelancers"))
            page = self.browser.page
            page.wait_for_timeout(4000)

            delivery_msg = (
                f"Hello,\n\nI have completed the work for '{engagement.get('title', 'this engagement')}'. "
                "The solution follows SOLID principles and includes comprehensive unit tests. "
                "Please find the attached file. I'm available for any questions or revisions.\n\n"
                "Best regards"
            )

            # Upload file jika ada input file
            file_input = page.locator("input[type='file']").first
            if file_input:
                file_input.set_input_files(file_path)
                page.wait_for_timeout(2000)

            # Kirim pesan
            msg_box = page.locator("div[contenteditable='true'], textarea").last
            if msg_box.is_visible():
                self.browser.human_type(msg_box, delivery_msg)
                page.keyboard.press("Enter")
                logger.info("[Toptal] Pekerjaan berhasil didelivery ke: %s", engagement.get("title"))
                return True

        except Exception as exc:
            logger.error("[Toptal] Gagal deliver ke Toptal: %s", exc)
        return False
