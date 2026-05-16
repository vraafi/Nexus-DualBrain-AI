"""
fiverr_agent.py
===============
Agent untuk platform Fiverr: manage gig orders yang masuk,
reply ke buyer, dan deliver hasil kerja.

FIX KRITIS: create_gig() dipecah menjadi beberapa execute_task terpisah
            (bukan satu task 40 langkah yang sangat mudah gagal).
            State machine approach — setiap step diverifikasi sebelum lanjut.

Reference state-machine browser automation pattern:
https://github.com/browser-use/browser-use/tree/main/examples (60k+ stars)
"""

import logging
import json
import time
import os

logger = logging.getLogger(__name__)

GIG_TEMPLATES = [
    {
        "niche": "python_automation",
        "title": "I will write a Python automation script for your task",
        "category": "Programming & Tech",
        "subcategory": "Scripts & Utilities",
        "tags": ["python script", "task automation", "file processing", "data automation", "python bot"],
        "basic": {
            "label": "Single Task",
            "desc": "One Python script, 1 specific task, error handling included. Delivered as .py file with usage instructions.",
            "price": 20, "days": 1, "revisions": 2,
        },
        "standard": {
            "label": "Multi-Feature Script",
            "desc": "Python script with up to 3 features, logging, unit tests, and a README. Clean and production-ready.",
            "price": 45, "days": 2, "revisions": 3,
        },
        "premium": {
            "label": "Full Automation Solution",
            "desc": "Complete automation solution: modular code, full test suite, scheduling support, and detailed documentation.",
            "price": 90, "days": 3, "revisions": 999,
        },
        "requirements": [
            "What task do you need automated? (Please be as specific as possible)",
            "What is the input? (e.g. CSV file, folder of files, API endpoint, website URL)",
            "What should the output look like? (e.g. CSV, JSON, printed report, modified files)",
            "Any specific Python libraries you prefer? (Leave blank if unsure — I will choose the best)",
        ],
        "description_prompt": (
            "Write a professional Fiverr gig description for a Python automation script service. "
            "The seller is a skilled Python developer who delivers clean, well-tested scripts. "
            "Rules:\n"
            "- Length: 1000 to 1200 characters (HARD LIMIT: do not exceed 1200)\n"
            "- Start with a strong hook sentence\n"
            "- Explain what buyer gets in each package (Basic/Standard/Premium)\n"
            "- List what the seller WON'T do: no GUI apps, no machine learning models, no mobile apps, no databases requiring a live server\n"
            "- Mention: Python 3.10+, requests, BeautifulSoup, Pandas, CSV/JSON output, unit tests\n"
            "- End with a clear call to action\n"
            "- Professional English only, no emojis, no contact info, no competitor platform names\n"
            "- Do NOT include markdown, headers, or bullet symbols — write as clean plain text paragraphs"
        ),
    },
    {
        "niche": "web_scraping",
        "title": "I will scrape website data and export it to CSV or JSON",
        "category": "Programming & Tech",
        "subcategory": "Data Processing",
        "tags": ["web scraping", "data extraction", "python scraper", "beautifulsoup", "csv export"],
        "basic": {
            "label": "Single Page Scrape",
            "desc": "Scrape one URL, up to 500 records, delivered as a clean CSV file.",
            "price": 25, "days": 1, "revisions": 2,
        },
        "standard": {
            "label": "Multi-Page Scraper",
            "desc": "Scrape multiple pages with pagination support. Delivered as CSV and JSON with a reusable Python script.",
            "price": 55, "days": 2, "revisions": 3,
        },
        "premium": {
            "label": "Full Scraping Pipeline",
            "desc": "Complete pipeline: scrape, clean, deduplicate, and export. Includes scheduling script and full documentation.",
            "price": 100, "days": 3, "revisions": 999,
        },
        "requirements": [
            "What is the URL of the website you want to scrape?",
            "What data fields do you need? (e.g. product name, price, URL, description)",
            "How many records do you estimate are on the site?",
            "Do you need the script delivered so you can re-run it yourself, or just the data file?",
        ],
        "description_prompt": (
            "Write a professional Fiverr gig description for a web scraping service using Python. "
            "The seller extracts structured data from websites and delivers clean CSV or JSON files. "
            "Rules:\n"
            "- Length: 1000 to 1200 characters (HARD LIMIT: do not exceed 1200)\n"
            "- Start with a strong hook sentence about data being valuable\n"
            "- Explain the 3 packages clearly (Basic: single page, Standard: multi-page, Premium: full pipeline)\n"
            "- List what the seller WON'T do: sites behind login without credentials, sites that explicitly ban scraping in ToS, real-time data streams, mobile apps\n"
            "- Mention tools: Python 3.10+, requests, BeautifulSoup, Pandas, rotating user-agents for reliability\n"
            "- End with a call to action to message before ordering\n"
            "- Professional English only, no emojis, no contact info\n"
            "- Do NOT include markdown, headers, or bullet symbols — write as clean plain text paragraphs"
        ),
    },
]


class FiverrAgent:
    def __init__(self, browser_agent, llm_client):
        self.browser = browser_agent
        self.llm = llm_client

    def login_fiverr(self) -> bool:
        """Login ke Fiverr menggunakan credential dari IdentityManager."""
        from identity_manager import IdentityManager
        identity = IdentityManager()
        creds = identity.get_credential("fiverr")
        if not creds:
            logger.error("[Fiverr] Tidak ada credential Fiverr di vault.")
            return False

        result = self.browser.execute_task(
            f"Login ke Fiverr di https://www.fiverr.com/login. "
            f"Email: {creds['username']}. Password: {creds['password']}. "
            f"Setelah login berhasil, konfirmasi dengan melihat dashboard seller.",
            max_steps=7
        )
        if "FAILED" in result:
            logger.error("[Fiverr] Login error.")
            return False

        logger.info("[Fiverr] Login berhasil.")
        return True

    def check_active_orders(self) -> list[dict]:
        """
        Cek daftar order aktif yang menunggu penyelesaian.
        Return list of dict: {order_id, buyer_name, title, description, deadline, url}
        """
        result = self.browser.execute_task(
            "Buka https://www.fiverr.com/orders/manage_orders. "
            "List semua order yang statusnya 'In Progress' atau aktif. "
            "Return JSON: [{order_id, buyer_name, title, deadline, url}, ...]",
            max_steps=8
        )
        try:
            match = __import__('re').search(r'\[.*?\]', result, __import__('re').DOTALL)
            if match:
                orders = json.loads(match.group(0))
                for o in orders:
                    o["platform"] = "fiverr"
                    o["description"] = ""
                logger.info("[Fiverr] Ditemukan %d order aktif.", len(orders))
                return orders
        except Exception as exc:
            logger.error("[Fiverr] Gagal cek order: %s", exc)
        return []

    def get_order_details(self, order: dict) -> dict:
        """Buka halaman detail order dan ambil requirement lengkap dari buyer."""
        if not order.get("url"):
            return order

        result = self.browser.execute_task(
            f"Buka url order Fiverr ini: {order['url']}. "
            f"Ambil requirement atau pesan dari buyer. "
            f"Return plain text yang berisi pesan dari buyer.",
            max_steps=6
        )
        if "FAILED" not in result:
            order["description"] = result
        return order

    def reply_to_buyer(self, order: dict, message: str) -> bool:
        """Kirim pesan balasan ke buyer di halaman order."""
        result = self.browser.execute_task(
            f"Buka halaman order Fiverr: {order.get('url')}. "
            f"Ketik pesan ini di chat box: {message}. "
            f"Klik tombol kirim pesan.",
            max_steps=8
        )
        return "FAILED" not in result

    def deliver_order(self, order: dict, file_path: str, delivery_message: str) -> bool:
        """
        Kirim delivery ke buyer — upload file hasil kerja + pesan pengiriman.
        Ini langkah final sebelum buyer review dan bayar.
        """
        result = self.browser.execute_task(
            f"Buka halaman order Fiverr: {order.get('url', 'https://www.fiverr.com/orders/manage_orders')}. "
            f"Klik tombol 'Deliver Now'. "
            f"Upload file dari path: {file_path}. "
            f"Tulis pesan delivery: {delivery_message[:200]}. "
            f"Klik Submit.",
            max_steps=10
        )
        return "FAILED" not in result

    def check_gig_count(self) -> int:
        """
        Cek jumlah Gig AKTIF (bukan draft) di halaman Manage Gigs.
        """
        result = self.browser.execute_task(
            "Buka dashboard seller Fiverr dan buka halaman Manage Gigs. "
            "Hitung jumlah gig yang berstatus 'Active'. "
            "Return JSON: {count: int}",
            max_steps=8
        )
        try:
            match = __import__('re').search(r'\{.*?\}', result, __import__('re').DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data.get("count", 0)
        except Exception:
            pass
        return 0

    def _generate_dynamic_template(self) -> dict:
        """
        Gunakan LLM untuk generate gig template unik.
        """
        prompt = (
            "Generate a JSON for a new Fiverr gig offering a unique Python automation or data scripting service. "
            "It must be a specific niche. Examples: 'Automate Excel to PDF', 'Automate API data sync', 'Python Crypto Bot', etc. "
            "Return ONLY valid JSON. Schema:\n"
            "{\n"
            '  "title": "I will [action in max 60 chars, no special chars]",\n'
            '  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],\n'
            '  "basic": {"label": "Basic", "desc": "Short desc", "price": 15, "days": 1, "revisions": 1},\n'
            '  "standard": {"label": "Standard", "desc": "Short desc", "price": 40, "days": 2, "revisions": 2},\n'
            '  "premium": {"label": "Premium", "desc": "Short desc", "price": 80, "days": 3, "revisions": 999},\n'
            '  "requirements": ["What is your target?"]\n'
            "}"
        )
        try:
            resp = self.llm.generate_content(prompt, use_negotiation_model=True) or ""
            start = resp.find('{')
            end = resp.rfind('}') + 1
            if start != -1 and end != 0:
                data = json.loads(resp[start:end])
                data["niche"] = "dynamic"
                data["description_prompt"] = (
                    f"Write a professional 1000 character Fiverr gig description for a service titled: "
                    f"'{data['title']}'. Emphasize Python and automation. Do NOT include markdown."
                )
                return data
        except Exception as e:
            logger.error("Gagal generate dynamic template: %s", e)
        return GIG_TEMPLATES[0]

    def _generate_gig_description(self, template: dict) -> str:
        """
        Generate deskripsi gig menggunakan LLM.
        Target: 1000-1200 karakter (aturan Fiverr 2026).
        """
        description = self.llm.generate_content(template.get("description_prompt", ""))

        if not description or len(description) < 100:
            description = (
                f"Welcome to my professional service!\n\n"
                f"I specialize in: {template.get('title', 'Python Automation')}.\n\n"
                "Are you tired of manual, repetitive tasks eating up your valuable time? "
                "I will write a clean, reliable, and highly efficient Python script tailored exactly to your needs.\n\n"
                "Basic package: Perfect for simple, single-step tasks.\n"
                "Standard package: Ideal for multi-step processes and pipelines.\n"
                "Premium package: A complete, robust solution with scheduling and full documentation.\n\n"
                "What I do NOT offer: GUI applications, mobile apps, or live production database administration.\n\n"
                "I pride myself on delivering clean, well-commented code that you can rely on. "
                "Please message me before placing an order to ensure we are perfectly aligned on the requirements."
            )

        if len(description) > 1200:
            description = description[:1197] + "..."
        logger.info("[Fiverr] Deskripsi gig: %d karakter.", len(description))
        return description

    def _click_next(self, page=None):
        """Helper backward compat."""
        pass

    def create_gig(self, template: dict = None) -> bool:
        """
        Buat Gig baru di Fiverr secara otomatis menggunakan STATE MACHINE approach.

        FIX KRITIS: Sebelumnya satu execute_task 40 langkah yang sangat mudah gagal.
        Sekarang dipecah menjadi 6 langkah kecil yang masing-masing diverifikasi.

        State machine pattern reference:
        https://github.com/browser-use/browser-use/tree/main/examples
        """
        if not template:
            template = self._generate_dynamic_template()

        logger.info("[Fiverr] Membuat Gig baru: '%s' ...", template.get("title", "Python Service"))
        description = self._generate_gig_description(template)

        img_path = os.path.join(os.getcwd(), "gig_image.jpg")
        try:
            import urllib.request
            safe_title = template["title"].replace(" ", "+")[:40]
            img_url = f"https://dummyimage.com/712x430/282c34/61dafb.jpg&text={safe_title}"
            urllib.request.urlretrieve(img_url, img_path)
        except Exception:
            pass

        # ── STATE 1: Navigasi ke halaman Create Gig ──────────────────────────
        logger.info("[Fiverr] State 1: Navigasi ke Create Gig...")
        step1 = self.browser.execute_task(
            "Buka https://www.fiverr.com/gigs/new. "
            "Pastikan halaman 'Overview' atau 'Create a New Gig' sudah terbuka. "
            "Konfirmasi dengan menyebut title atau elemen halaman yang terlihat.",
            max_steps=5
        )
        if "FAILED" in step1:
            logger.error("[Fiverr] Gagal navigasi ke Create Gig.")
            return False
        time.sleep(2)

        # ── STATE 2: Isi Overview (Title, Category, Tags) ────────────────────
        logger.info("[Fiverr] State 2: Isi Overview...")
        tags_str = ", ".join(template.get("tags", [])[:5])
        step2 = self.browser.execute_task(
            f"Di halaman Fiverr Create Gig, isi field-field berikut:\n"
            f"1. Judul gig: '{template['title']}'\n"
            f"2. Pilih Category: 'Programming & Tech'\n"
            f"3. Tambahkan tags: {tags_str}\n"
            f"Setelah semua terisi, klik tombol 'Save & Continue'.",
            max_steps=8
        )
        if "FAILED" in step2:
            logger.error("[Fiverr] Gagal isi Overview.")
            return False
        time.sleep(2)

        # ── STATE 3: Isi Pricing ─────────────────────────────────────────────
        logger.info("[Fiverr] State 3: Isi Pricing...")
        basic = template.get("basic", {})
        standard = template.get("standard", {})
        premium = template.get("premium", {})
        step3 = self.browser.execute_task(
            f"Di halaman Fiverr Pricing, isi paket harga:\n"
            f"Basic: nama '{basic.get('label', 'Basic')}', "
            f"harga ${basic.get('price', 20)}, "
            f"delivery {basic.get('days', 1)} hari, "
            f"revisi {basic.get('revisions', 2)}x, "
            f"deskripsi: '{basic.get('desc', 'Basic service')}'\n"
            f"Standard: nama '{standard.get('label', 'Standard')}', "
            f"harga ${standard.get('price', 45)}, "
            f"delivery {standard.get('days', 2)} hari\n"
            f"Premium: nama '{premium.get('label', 'Premium')}', "
            f"harga ${premium.get('price', 90)}, "
            f"delivery {premium.get('days', 3)} hari\n"
            f"Klik 'Save & Continue'.",
            max_steps=10
        )
        if "FAILED" in step3:
            logger.error("[Fiverr] Gagal isi Pricing.")
            return False
        time.sleep(2)

        # ── STATE 4: Isi Description & FAQ ───────────────────────────────────
        logger.info("[Fiverr] State 4: Isi Description...")
        step4 = self.browser.execute_task(
            f"Di halaman Fiverr Description, isi field deskripsi dengan teks berikut "
            f"(salin persis, tidak perlu tambahan apapun):\n"
            f"'{description[:1000]}'\n"
            f"Klik 'Save & Continue'.",
            max_steps=8
        )
        if "FAILED" in step4:
            logger.error("[Fiverr] Gagal isi Description.")
            return False
        time.sleep(2)

        # ── STATE 5: Isi Requirements ────────────────────────────────────────
        logger.info("[Fiverr] State 5: Isi Requirements...")
        requirements = template.get("requirements", ["Please describe your task in detail."])
        req_text = requirements[0] if requirements else "Please describe your task in detail."
        step5 = self.browser.execute_task(
            f"Di halaman Fiverr Requirements, tambahkan buyer requirement:\n"
            f"Pertanyaan: '{req_text}'\n"
            f"Pastikan tipe pertanyaan adalah 'Free Text'. "
            f"Tandai sebagai 'Required'. "
            f"Klik 'Save & Continue'.",
            max_steps=7
        )
        if "FAILED" in step5:
            logger.warning("[Fiverr] Gagal isi Requirements, lanjut ke Gallery.")
        time.sleep(2)

        # ── STATE 6: Upload Gallery Image & Publish ──────────────────────────
        logger.info("[Fiverr] State 6: Upload image & Publish...")
        step6 = self.browser.execute_task(
            f"Di halaman Fiverr Gallery, upload file gambar dari path: '{img_path}'. "
            f"Tunggu sampai upload selesai. "
            f"Klik tombol 'Save & Continue' atau 'Publish'. "
            f"Jika ada preview/publish button, klik untuk mempublikasikan gig.",
            max_steps=10
        )
        if "FAILED" in step6:
            logger.error("[Fiverr] Gagal upload gallery/publish.")
            return False

        logger.info("[Fiverr] Gig '%s' berhasil dibuat dan dipublikasikan.", template.get("title"))
        return True

    def ensure_gig_exists(self) -> bool:
        """
        Cek jumlah Gig. Jika kurang dari 5, buat Gig baru secara dinamis.
        """
        count = self.check_gig_count()
        if count >= 5:
            logger.info("[Fiverr] Sudah ada %d Gig. Cukup untuk saat ini.", count)
            return True

        logger.info("[Fiverr] Hanya ada %d Gig. Membuat Gig dinamis baru...", count)
        success = self.create_gig()

        if success:
            logger.info("[Fiverr] Gig dinamis berhasil dibuat dan dipublikasikan.")
        else:
            logger.warning("[Fiverr] Gagal mempublikasikan Gig. Mungkin ada mandatory field yang terlewat.")
        return success

    def search_and_offer_gigs(self) -> bool:
        """
        Aktif di Fiverr Buyer Request atau optimasi Gig ranking.
        """
        result = self.browser.execute_task(
            "Buka https://www.fiverr.com/users/selling/buyer_requests. "
            "Cari request dari buyer. Jika ada, buat offer singkat yang profesional (max 100 kata) "
            "dan kirim offer tersebut. Return 'BERHASIL' jika mengirim offer, atau 'TIDAK_ADA' jika kosong.",
            max_steps=10
        )
        return "BERHASIL" in result
