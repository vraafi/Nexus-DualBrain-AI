import logging
import time
import os
from dotenv import load_dotenv

class FreelanceWorkflow:
    def __init__(self, browser_agent, llm_client, database):
        self.browser = browser_agent
        self.llm = llm_client
        self.db = database
        load_dotenv()

    def load_api_keys(self):
        """Securely loads Google AI Studio API keys from .env file for 100% autonomy."""
        logging.info("Loading Google AI Studio API keys from environment...")
        keys_loaded = 0
        for i in range(1, 11):
            env_key = os.getenv(f"GOOGLE_AI_STUDIO_KEY_{i}")
            if env_key and env_key not in self.llm.api_keys:
                self.llm.api_keys.append(env_key)
                keys_loaded += 1

        if len(self.llm.api_keys) < 10:
            logging.warning(f"Only loaded {len(self.llm.api_keys)}/10 API keys. The system requires 10 for optimal rotation. Please update .env")
        else:
            logging.info("Successfully loaded 10 API keys from environment.")

    def handle_freelance_platforms(self):
        """Simulates interacting with Upwork, Fiverr, and Toptal based on branding guidelines."""
        logging.info("Starting freelance platform interaction sequence...")
        self.db.update_task_state("freelance_platforms", "IN_PROGRESS")

        platforms = [
            {"name": "Upwork", "url": "https://www.upwork.com"},
            {"name": "Fiverr", "url": "https://www.fiverr.com"},
            {"name": "Toptal", "url": "https://www.toptal.com"}
        ]

        try:
            for platform in platforms:
                logging.info(f"Navigating to {platform['name']} ({platform['url']})...")
                success = self.browser.get(platform["url"])
                if not success:
                    logging.error(f"Failed to load {platform['name']}")
                    continue

                logging.info(f"Checking for messages and new job postings on {platform['name']}...")
                self.browser.random_delay()

                # Dynamic Reasoning: Ask LLM to evaluate a hypothetical job posting context
                # In a real environment, this text would be scraped from the UI
                simulated_job_context = (
                    f"Platform: {platform['name']}. Klien membutuhkan seorang developer untuk memperbaiki bug "
                    "skrip scraping Python mereka yang macet karena deteksi bot."
                )

                dynamic_prompt = (
                    f"Evaluasi peluang pekerjaan ini secara otonom: '{simulated_job_context}'. "
                    "Jika pekerjaan ini 100% dapat saya selesaikan secara otomatis tanpa bantuan manusia, "
                    "buatkan pesan penawaran (proposal) profesional berdasarkan pedoman branding saya "
                    "sebagai 'Problem Solver' atau 'Konsultan Teknis'. Jika tidak, jawab 'TIDAK_LAYAK'."
                )

                logging.info("Requesting LLM dynamic evaluation of job prospect...")
                evaluation = self.llm.generate_text(dynamic_prompt)

                if "TIDAK_LAYAK" not in evaluation and "Error" not in evaluation:
                    logging.info(f"Job deemed suitable. Generated Proposal:\n{evaluation}")
                    # Simulate sending the proposal
                    self.browser.random_delay(1.0, 3.0)
                    logging.info(f"Proposal sent on {platform['name']}")
                else:
                    logging.info(f"Job rejected or failed evaluation. Moving on.")

                # Negotiation Fallback Check (simulated)
                simulated_client_reply = True # Set True to simulate a client negotiation
                if simulated_client_reply:
                     logging.info(f"Client replied on {platform['name']}. Consulting LLM for negotiation...")
                     negotiation_prompt = (
                         f"Klien dari {platform['name']} membalas: 'Harganya terlalu mahal, bisa diskon?'. "
                         "Saya hanya agent perantara. Berikan saran balasan negosiasi yang sopan dan profesional "
                         "yang mempertahankan harga (tiered pricing) sesuai branding."
                     )
                     advice = self.llm.generate_text(negotiation_prompt)
                     logging.info(f"LLM Negotiation Advice:\n{advice}")

        except Exception as e:
             logging.error(f"Error during freelance platform interaction: {e}")
             self.browser.quit()
             self.db.update_task_state("freelance_platforms", "FAILED", str(e))
             return False

        self.db.update_task_state("freelance_platforms", "COMPLETED")
        return True

    def manage_github_and_jules(self, client_id="pelanggan_01"):
        """Creates a GitHub repo and interacts with Jules for coding tasks."""
        logging.info(f"Starting GitHub and Jules interaction for client {client_id}...")
        self.db.update_task_state("github_jules", "IN_PROGRESS")

        try:
            # 1. Create GitHub Repository
            logging.info(f"Navigating to GitHub to create repo for {client_id}...")
            success = self.browser.get("https://github.com/new")
            if not success:
                raise Exception("Failed to load GitHub.")

            # Simulate UI interaction to create repo named "pelanggan_01"
            time.sleep(2)
            repo_url = f"https://github.com/my-agent-account/{client_id}"
            logging.info(f"Simulated creation of repository: {repo_url}")

            # 2. Interact with Jules for coding
            logging.info("Navigating to https://jules.google.com ...")
            success = self.browser.get("https://jules.google.com")
            if not success:
                raise Exception("Failed to load Jules website.")

            time.sleep(3)
            # Simulate sending the request to Jules
            jules_prompt = (
                f"Tugas: Buatkan kode untuk client {client_id}. "
                "Peringatan: Akan ada update pada kode yang bisa jadi merubah "
                "atau menambahkan banyak hal dari rencana awal ini."
            )
            logging.info(f"Simulated sending prompt to Jules: {jules_prompt}")

            # 3. Simulate receiving code and passing it to the Sandbox Tester (handled outside this class)
            logging.info("Code generation complete. Ready for sandbox testing.")

        except Exception as e:
            logging.error(f"Error during GitHub/Jules interaction: {e}")
            self.browser.quit()
            self.db.update_task_state("github_jules", "FAILED", str(e))
            return False

        self.db.update_task_state("github_jules", "COMPLETED")
        return True
