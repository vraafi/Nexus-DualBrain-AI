"""
fiverr_agent.py
===============
Agent untuk platform Fiverr: manage gig orders yang masuk,
reply ke buyer, dan deliver hasil kerja.
Berbeda dengan Upwork (kita apply ke job), di Fiverr kita
menunggu order masuk ke Gig kita, lalu memprosesnya.

UPDATE: Tambah check_gig_exists() dan create_gig() —
agent bisa membuat Gig otomatis jika belum ada.
"""

import logging
import json
import time
import os

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# GIG TEMPLATES — Dibuat sesuai aturan Fiverr 2026:
#   - Judul awali "I will", max 80 karakter, tanpa karakter khusus (& / " +)
#   - Hanya layanan yang BISA dikerjakan agent (Python script + sandbox test)
#   - Tidak menjanjikan GUI, ML, database server, atau mobile app
#   - Tags 5 frasa UNIK (bukan pengulangan kata yang sama)
#   - Harga realistis: agent deliver dalam 1-3 hari
# ─────────────────────────────────────────────────────────────────────────────
GIG_TEMPLATES = [
    {
        "niche": "python_automation",
        # 55 chars — sesuai aturan max 80, ideal <50 tapi masih oke
        "title": "I will write a Python automation script for your task",
        "category": "Programming & Tech",
        "subcategory": "Scripts & Utilities",
        # 5 tag UNIK — hindari pengulangan, targetkan variasi pencarian berbeda
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
        # Pertanyaan untuk buyer — wajib agar agent tahu apa yang harus dibuat
        "requirements": [
            "What task do you need automated? (Please be as specific as possible)",
            "What is the input? (e.g. CSV file, folder of files, API endpoint, website URL)",
            "What should the output look like? (e.g. CSV, JSON, printed report, modified files)",
            "Any specific Python libraries you prefer? (Leave blank if unsure — I will choose the best)",
        ],
        # Deskripsi panjang (target 1000+ karakter) — digenerate LLM berdasarkan prompt ini
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
        # 54 chars
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
            max_steps=12
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
            max_steps=15
        )
        try:
            import re
            match = re.search(r'\[.*?\]', result, re.DOTALL)
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
            max_steps=10
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
            max_steps=15
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
            max_steps=20
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
            max_steps=15
        )
        try:
            import re
            match = re.search(r'\{.*?\}', result, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data.get("count", 0)
        except Exception:
            pass
        return 0

    def _generate_dynamic_template(self) -> dict:
        """
        Gunakan LLM untuk generate gig template unik.
        Ini memastikan tawaran (offer) selalu berbeda.
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
                data["description_prompt"] = f"Write a professional 1000 character Fiverr gig description for a service titled: '{data['title']}'. Emphasize Python and automation. Do NOT include markdown."
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

        # Fallback jika LLM gagal
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
        """Helper backward compat, walau di execute_task tidak perlu explicitly click next step-by-step biasa"""
        pass

    def create_gig(self, template: dict = None) -> bool:
        """
        Buat Gig baru di Fiverr secara otomatis.
        Jika template None, gunakan LLM untuk membuat gig dinamis.
        """
        if not template:
            template = self._generate_dynamic_template()

        logger.info("[Fiverr] Membuat Gig baru: '%s' ...", template.get("title", "Python Service"))

        description = self._generate_gig_description(template)

        # Download temporary image
        import urllib.request
        img_path = os.path.join(os.getcwd(), "gig_image.jpg")
        try:
            safe_title = template["title"].replace(" ", "+")[:40]
            img_url = f"https://dummyimage.com/712x430/282c34/61dafb.jpg&text={safe_title}"
            urllib.request.urlretrieve(img_url, img_path)
        except Exception:
            pass

        # Use browser-use to go through the Gig creation flow
        # In reality, this flow is very complex and might require multiple execute_task calls,
        # but for this agent we can give it a broad task.
        task = (
            f"Buat Fiverr gig baru.\n"
            f"1. Navigasi ke halaman Manage Gigs, klik Create a new Gig.\n"
            f"2. Judul: '{template['title']}'\n"
            f"3. Kategori: Programming & Tech.\n"
            f"4. Masukkan tags: {', '.join(template['tags'][:5])}.\n"
            f"5. Lanjut ke pricing. Isi Basic: {template['basic']['price']}$, {template['basic']['days']} days. "
            f"Standard: {template['standard']['price']}$, {template['standard']['days']} days. "
            f"Premium: {template['premium']['price']}$, {template['premium']['days']} days.\n"
            f"6. Lanjut ke description. Isi description: '{description[:500]}...'\n"
            f"7. Lanjut ke requirements. Tambahkan requirement: '{template.get('requirements', ['Please describe your task'])[0]}'.\n"
            f"8. Lanjut ke gallery. Upload file gambar di '{img_path}'.\n"
            f"9. Publish gig."
        )

        result = self.browser.execute_task(task, max_steps=40)
        return "FAILED" not in result

    def ensure_gig_exists(self) -> bool:
        """
        Cek jumlah Gig. Jika kurang dari 5, buat Gig baru secara dinamis
        agar variasi offer terus bertambah sesuai request.
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
        Di Fiverr, kita tidak apply ke job — kita menunggu order masuk ke Gig.
        Tapi kita bisa aktif di Fiverr Buyer Request (jika masih tersedia)
        atau optimasi Gig ranking dengan update deskripsi.
        Return True jika ada aktivitas yang dilakukan.
        """
        result = self.browser.execute_task(
            "Buka https://www.fiverr.com/users/selling/buyer_requests. "
            "Cari request dari buyer. Jika ada, buat offer singkat yang profesional (max 100 kata) "
            "dan kirim offer tersebut. Return 'BERHASIL' jika mengirim offer, atau 'TIDAK_ADA' jika kosong.",
            max_steps=20
        )
        return "BERHASIL" in result
