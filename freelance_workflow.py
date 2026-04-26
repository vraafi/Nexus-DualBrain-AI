import logging
import time

class FreelanceWorkflow:
    def __init__(self, browser_agent, llm_client, database):
        self.browser = browser_agent
        self.llm = llm_client
        self.db = database

    def check_and_request_api_keys(self):
        """Checks if the required Google AI Studio API keys are present in memory/env."""
        logging.info("Checking for required API keys...")
        if len(self.llm.api_keys) < 10:
            logging.warning("Less than 10 API keys found. Requesting user input...")
            missing_keys_count = 10 - len(self.llm.api_keys)
            print(f"Sistem membutuhkan 10 Google AI Studio API Keys. Kurang {missing_keys_count} key.")
            for i in range(missing_keys_count):
                user_key = input(f"Masukkan API Key ke-{len(self.llm.api_keys) + 1}: ")
                if user_key.strip():
                    self.llm.api_keys.append(user_key.strip())
            logging.info("API keys populated from user input.")

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

                # Simulate checking messages and applying branding rules
                logging.info(f"Applying branding rules and checking messages on {platform['name']}...")
                time.sleep(2) # Simulate UI interaction time

                # Logic dictates we act as a messenger and ask Gemini Pro for advice if there's an issue
                # Simulated issue detection:
                simulated_issue_found = False # Set to True to test the Gemini Pro negotiation fallback
                if simulated_issue_found:
                    logging.warning(f"Issue found on {platform['name']}. Consulting Gemini Pro...")
                    advice = self.llm.generate_text("Ada masalah negosiasi dengan klien di platform freelance. Tolong berikan saran membalas sebagai profesional berdasarkan pedoman branding saya.")
                    logging.info(f"Advice from Gemini: {advice}")

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
