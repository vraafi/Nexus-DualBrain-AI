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

        try:
            self.browser.navigate("https://www.fiverr.com/login")
            page = self.browser.page
            page.wait_for_timeout(3000)

            # Input email
            email_input = page.locator("input[name='email'], input[type='email']").first
            self.browser.human_type(email_input, creds["username"])

            # Input password
            password_input = page.locator("input[name='password'], input[type='password']").first
            self.browser.human_type(password_input, creds["password"])

            # Submit
            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            if "login" in page.url:
                logger.warning("[Fiverr] Login gagal atau perlu 2FA manual.")
                page.wait_for_timeout(15000)
                if "login" in page.url:
                    return False

            logger.info("[Fiverr] Login berhasil.")
            return True

        except Exception as exc:
            logger.error("[Fiverr] Login error: %s", exc)
            return False

    def check_active_orders(self) -> list[dict]:
        """
        Cek daftar order aktif yang menunggu penyelesaian.
        Return list of dict: {order_id, buyer_name, title, description, deadline, url}
        """
        orders = []
        try:
            self.browser.navigate("https://www.fiverr.com/orders/manage_orders")
            page = self.browser.page
            page.wait_for_timeout(5000)

            # Cari order cards yang aktif
            order_cards = page.locator("div.order-container, article.order-card, div[class*='order-row']").all()

            for card in order_cards[:5]:
                try:
                    title_elem = card.locator("h3, span[class*='title'], a[class*='title']").first
                    title = title_elem.inner_text() if title_elem.is_visible() else "Unknown Order"

                    buyer_elem = card.locator("span[class*='buyer'], a[class*='buyer']").first
                    buyer = buyer_elem.inner_text() if buyer_elem.is_visible() else "Unknown Buyer"

                    order_link = card.locator("a[href*='/orders/']").first
                    url = order_link.get_attribute("href") if order_link.is_visible() else ""
                    if url and not url.startswith("http"):
                        url = "https://www.fiverr.com" + url

                    orders.append({
                        "order_id": url.split("/")[-1] if url else f"order_{len(orders)}",
                        "buyer_name": buyer,
                        "title": title,
                        "description": "",  # akan diisi saat buka detail
                        "url": url,
                        "platform": "fiverr"
                    })
                except Exception as card_err:
                    logger.warning("[Fiverr] Gagal parse order card: %s", card_err)

            logger.info("[Fiverr] Ditemukan %d order aktif.", len(orders))
            return orders

        except Exception as exc:
            logger.error("[Fiverr] Gagal cek order: %s", exc)
            return []

    def get_order_details(self, order: dict) -> dict:
        """Buka halaman detail order dan ambil requirement lengkap dari buyer."""
        if not order.get("url"):
            return order
        try:
            self.browser.navigate(order["url"])
            page = self.browser.page
            page.wait_for_timeout(4000)

            # Ambil requirement / pesan dari buyer
            req_elem = page.locator("div[class*='requirements'], div[class*='buyer-message'], p[class*='requirement']").first
            if req_elem.is_visible():
                order["description"] = req_elem.inner_text()

        except Exception as exc:
            logger.warning("[Fiverr] Gagal ambil detail order %s: %s", order.get("order_id"), exc)
        return order

    def reply_to_buyer(self, order: dict, message: str) -> bool:
        """Kirim pesan balasan ke buyer di halaman order."""
        try:
            if order.get("url"):
                self.browser.navigate(order["url"])
            page = self.browser.page
            page.wait_for_timeout(3000)

            msg_box = page.locator("div[contenteditable='true'], textarea[placeholder*='message']").last
            if msg_box.is_visible():
                self.browser.human_type(msg_box, message)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2000)
                logger.info("[Fiverr] Pesan terkirim ke buyer %s.", order.get("buyer_name"))
                return True
        except Exception as exc:
            logger.error("[Fiverr] Gagal reply ke buyer: %s", exc)
        return False

    def deliver_order(self, order: dict, file_path: str, delivery_message: str) -> bool:
        """
        Kirim delivery ke buyer — upload file hasil kerja + pesan pengiriman.
        Ini langkah final sebelum buyer review dan bayar.
        """
        try:
            self.browser.navigate(order.get("url", "https://www.fiverr.com/orders/manage_orders"))
            page = self.browser.page
            page.wait_for_timeout(3000)

            # Klik tombol Deliver Now
            deliver_btn = page.get_by_role("button", name="Deliver Now")
            if not deliver_btn.is_visible():
                deliver_btn = page.locator("button:has-text('Deliver'), a:has-text('Deliver Now')").first

            if deliver_btn.is_visible():
                self.browser.human_click(deliver_btn)
                page.wait_for_timeout(3000)

            # Upload file
            file_input = page.locator("input[type='file']").first
            if file_input:
                file_input.set_input_files(file_path)
                page.wait_for_timeout(3000)

            # Tulis pesan delivery
            msg_box = page.locator("textarea[placeholder*='delivery'], div[contenteditable][class*='delivery']").first
            if msg_box.is_visible():
                self.browser.human_type(msg_box, delivery_message)

            # Submit delivery
            submit_btn = page.get_by_role("button", name="Submit")
            if not submit_btn.is_visible():
                submit_btn = page.locator("button:has-text('Submit Delivery')").first
            self.browser.human_click(submit_btn)
            page.wait_for_timeout(3000)

            logger.info("[Fiverr] Order %s berhasil di-deliver.", order.get("order_id"))
            return True

        except Exception as exc:
            logger.error("[Fiverr] Gagal deliver order: %s", exc)
            return False

    def check_gig_exists(self) -> bool:
        """
        Cek apakah seller sudah punya Gig aktif di Fiverr.
        Return True jika ada, False jika belum ada gig sama sekali.
        """
        try:
            page = self.browser.page
            self.browser.navigate("https://www.fiverr.com/seller_dashboard")
            page.wait_for_timeout(4000)

            # Cek tombol atau link ke gig yang sudah ada
            gig_items = page.locator("li[class*='gig'], div[class*='gig-card'], a[href*='/gigs/']").all()
            if gig_items:
                logger.info("[Fiverr] Gig sudah ada (%d ditemukan).", len(gig_items))
                return True

            # Alternatif: cek di halaman manage gigs
            self.browser.navigate("https://www.fiverr.com/seller_dashboard/gigs")
            page.wait_for_timeout(4000)
            gig_items = page.locator("li[class*='gig'], tr[class*='gig'], div[class*='gig-wrapper']").all()
            if gig_items:
                logger.info("[Fiverr] Gig sudah ada di manage gigs (%d ditemukan).", len(gig_items))
                return True

            logger.info("[Fiverr] Tidak ada Gig aktif ditemukan.")
            return False

        except Exception as exc:
            logger.warning("[Fiverr] Gagal cek gig: %s", exc)
            return False

    def _generate_gig_description(self, template: dict) -> str:
        """
        Generate deskripsi gig menggunakan LLM.
        Target: 1000-1200 karakter (aturan Fiverr 2026).
        """
        description = self.llm.generate_content(template["description_prompt"])

        # Fallback jika LLM gagal — teks statis yang sudah dihitung 1100 karakter
        if not description:
            if template["niche"] == "python_automation":
                description = (
                    "Tired of repeating the same manual tasks every day? I will write a clean, "
                    "reliable Python script that automates your workflow so you can focus on what matters.\n\n"
                    "I am a Python developer specializing in task automation, file processing, and "
                    "data pipelines. Every script I deliver is tested, documented, and ready to run "
                    "on your machine with a single command.\n\n"
                    "Basic package: You get one Python script that handles a single, well-defined task. "
                    "It includes error handling and a short usage guide. Delivered in 24 hours.\n\n"
                    "Standard package: Up to three features combined in one script, with logging, "
                    "unit tests, and a README file. Clean, modular code you can easily extend yourself.\n\n"
                    "Premium package: A complete automation solution with a full test suite, scheduling "
                    "support, and detailed documentation. Production-ready from day one.\n\n"
                    "What I do NOT offer: GUI desktop applications, machine learning models, live database "
                    "servers, or mobile applications. My focus is pure Python scripts that run from the "
                    "command line or a scheduler.\n\n"
                    "Tools I use: Python 3.10+, requests, Pandas, openpyxl, schedule, and the standard library.\n\n"
                    "Message me before ordering so I can confirm your task is a good fit. I respond within a few hours."
                )
            else:
                description = (
                    "Data is the new currency, and I will collect it for you. I will scrape any "
                    "publicly accessible website and deliver the data as a clean, structured CSV or JSON file.\n\n"
                    "I have built scrapers for e-commerce sites, job boards, news portals, and "
                    "directories. Every script uses rotating user-agents and polite request delays to "
                    "stay reliable without triggering blocks.\n\n"
                    "Basic package: Scrape one page or one category, up to 500 records, delivered "
                    "as a CSV file within 24 hours.\n\n"
                    "Standard package: Multi-page scraping with full pagination support. You receive "
                    "both a CSV and JSON file plus the reusable Python script.\n\n"
                    "Premium package: A complete data pipeline — scrape, deduplicate, clean, and "
                    "schedule. Includes a scheduling script so you can refresh the data automatically.\n\n"
                    "What I do NOT scrape: sites that require login without you supplying credentials, "
                    "sites that explicitly prohibit scraping in their Terms of Service, or real-time "
                    "financial data streams.\n\n"
                    "Tools: Python 3.10+, requests, BeautifulSoup4, Pandas, lxml.\n\n"
                    "Please message me with the site URL before ordering so I can confirm feasibility."
                )

        # Potong jika melebihi 1200 karakter (batas keras Fiverr)
        if len(description) > 1200:
            description = description[:1197] + "..."
        logger.info("[Fiverr] Deskripsi gig: %d karakter.", len(description))
        return description

    def create_gig(self, template_index: int = 0) -> bool:
        """
        Buat Gig baru di Fiverr secara otomatis — sesuai aturan Fiverr 2026:
        - Judul "I will...", max 80 karakter
        - Deskripsi 1000-1200 karakter
        - 5 tag unik
        - 3 paket harga (Basic / Standard / Premium)
        - Buyer requirements untuk agen tahu apa yang harus dikerjakan
        """
        template = GIG_TEMPLATES[template_index % len(GIG_TEMPLATES)]
        logger.info("[Fiverr] Membuat Gig baru: '%s' ...", template["title"])

        description = self._generate_gig_description(template)

        try:
            page = self.browser.page
            self.browser.navigate("https://www.fiverr.com/gigs/new")
            page.wait_for_timeout(6000)

            # ── Step 1: Judul Gig ──────────────────────────────────────────
            # Selector luas — Fiverr sering update class names
            title_input = page.locator(
                "input[name='title'], input[placeholder*='title' i], "
                "input[data-field='title'], input[id*='title']"
            ).first
            if not title_input.is_visible(timeout=8000):
                logger.warning("[Fiverr] Input judul tidak ditemukan.")
                return False
            title_input.triple_click()
            self.browser.human_type(title_input, template["title"])
            page.wait_for_timeout(1000)

            # ── Step 2: Kategori — Programming & Tech ─────────────────────
            # Fiverr pakai dropdown atau combo — coba keduanya
            cat_selectors = [
                "select[name='category_id']",
                "div[data-testid='category-select']",
                "div[class*='category'] button",
                "button[aria-label*='category' i]",
            ]
            for sel in cat_selectors:
                cat_el = page.locator(sel).first
                if cat_el.is_visible(timeout=2000):
                    self.browser.human_click(cat_el)
                    page.wait_for_timeout(1500)
                    # Coba pilih opsi Programming
                    opt = page.locator(
                        "option:has-text('Programming'), "
                        "li:has-text('Programming'), "
                        "div[role='option']:has-text('Programming')"
                    ).first
                    if opt.is_visible(timeout=2000):
                        self.browser.human_click(opt)
                        page.wait_for_timeout(1000)
                    break

            # ── Step 3: 5 Tags unik ────────────────────────────────────────
            tag_input = page.locator(
                "input[placeholder*='tag' i], input[name*='tag'], "
                "div[class*='tags'] input, input[data-field='tags']"
            ).first
            if tag_input.is_visible(timeout=3000):
                for tag in template["tags"][:5]:
                    tag_input.click()
                    page.wait_for_timeout(300)
                    self.browser.human_type(tag_input, tag)
                    page.wait_for_timeout(500)
                    # Tekan Enter atau klik opsi dropdown yang muncul
                    suggestion = page.locator(
                        f"li:has-text('{tag}'), div[role='option']:has-text('{tag}')"
                    ).first
                    if suggestion.is_visible(timeout=1500):
                        self.browser.human_click(suggestion)
                    else:
                        page.keyboard.press("Enter")
                    page.wait_for_timeout(600)

            # ── Step 4: Lanjut ke step berikutnya ─────────────────────────
            self._click_next(page)
            page.wait_for_timeout(4000)

            # ── Step 5: Deskripsi (1000-1200 karakter) ────────────────────
            desc_box = page.locator(
                "div[contenteditable='true'], textarea[name='description'], "
                "div[class*='description-input'] div[contenteditable]"
            ).first
            if desc_box.is_visible(timeout=8000):
                self.browser.human_click(desc_box)
                page.wait_for_timeout(500)
                # Gunakan keyboard shortcut untuk clear dan isi ulang
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                self.browser.human_type(desc_box, description)
                page.wait_for_timeout(1000)

            # ── Step 6: Paket Harga ────────────────────────────────────────
            for pkg_key in ["basic", "standard", "premium"]:
                pkg = template[pkg_key]
                try:
                    # Label paket
                    lbl = page.locator(
                        f"input[name*='{pkg_key}'][name*='name'], "
                        f"input[data-package='{pkg_key}'][name*='name'], "
                        f"input[placeholder*='{pkg_key}' i]"
                    ).first
                    if lbl.is_visible(timeout=2000):
                        lbl.triple_click()
                        self.browser.human_type(lbl, pkg["label"])

                    # Harga
                    price_inp = page.locator(
                        f"input[name*='{pkg_key}'][name*='price'], "
                        f"input[data-package='{pkg_key}'][name*='price']"
                    ).first
                    if price_inp.is_visible(timeout=2000):
                        price_inp.triple_click()
                        self.browser.human_type(price_inp, str(pkg["price"]))

                    # Waktu pengiriman
                    delivery_sel = page.locator(
                        f"select[name*='{pkg_key}'][name*='delivery'], "
                        f"select[data-package='{pkg_key}']"
                    ).first
                    if delivery_sel.is_visible(timeout=2000):
                        delivery_sel.select_option(str(pkg["days"]))

                    # Revisi
                    rev_sel = page.locator(
                        f"select[name*='{pkg_key}'][name*='revision'], "
                        f"select[data-package='{pkg_key}'][name*='revision']"
                    ).first
                    if rev_sel.is_visible(timeout=2000):
                        rev_val = "unlimited" if pkg["revisions"] == 999 else str(pkg["revisions"])
                        rev_sel.select_option(rev_val)

                    page.wait_for_timeout(500)
                except Exception as pkg_err:
                    logger.warning("[Fiverr] Gagal isi paket %s: %s", pkg_key, pkg_err)

            # ── Step 7: Lanjut ke Buyer Requirements ──────────────────────
            self._click_next(page)
            page.wait_for_timeout(4000)

            # ── Step 8: Buyer Requirements ─────────────────────────────────
            # Pertanyaan ini memastikan agent mendapat info cukup dari buyer
            add_req_btn = page.locator(
                "button:has-text('Add Requirement'), "
                "button:has-text('Add Question'), "
                "a:has-text('Add Requirement')"
            ).first
            for req_text in template.get("requirements", []):
                try:
                    if add_req_btn.is_visible(timeout=3000):
                        self.browser.human_click(add_req_btn)
                        page.wait_for_timeout(1500)
                    req_input = page.locator(
                        "input[placeholder*='requirement' i], "
                        "textarea[placeholder*='question' i], "
                        "div[class*='requirement'] input"
                    ).last
                    if req_input.is_visible(timeout=3000):
                        self.browser.human_type(req_input, req_text)
                        # Tandai sebagai required
                        req_checkbox = page.locator(
                            "input[type='checkbox'][name*='required'], "
                            "label:has-text('Required')"
                        ).last
                        if req_checkbox.is_visible(timeout=2000):
                            self.browser.human_click(req_checkbox)
                        page.wait_for_timeout(500)
                except Exception as req_err:
                    logger.warning("[Fiverr] Gagal tambah requirement: %s", req_err)

            # ── Step 9: Lanjut ke Publish ──────────────────────────────────
            self._click_next(page)
            page.wait_for_timeout(4000)

            # ── Step 10: Publish Gig ───────────────────────────────────────
            publish_btn = page.locator(
                "button:has-text('Publish'), button:has-text('Save & Publish'), "
                "button:has-text('Publish Gig')"
            ).first
            if publish_btn.is_visible(timeout=10000):
                self.browser.human_click(publish_btn)
                page.wait_for_timeout(6000)
                logger.info("[Fiverr] Gig '%s' berhasil dipublikasikan!", template["title"])
                return True
            else:
                logger.warning("[Fiverr] Tombol Publish tidak muncul — mungkin ada validasi yang belum terpenuhi atau perlu review manual Fiverr.")
                return False

        except Exception as exc:
            logger.error("[Fiverr] Gagal membuat Gig: %s", exc)
            return False

    def _click_next(self, page):
        """Helper: klik tombol Next / Save & Continue."""
        next_btn = page.locator(
            "button:has-text('Next'), button:has-text('Save & Continue'), "
            "button:has-text('Continue'), a:has-text('Next')"
        ).first
        if next_btn.is_visible(timeout=5000):
            self.browser.human_click(next_btn)
        else:
            logger.warning("[Fiverr] Tombol Next tidak ditemukan.")

    def ensure_gig_exists(self) -> bool:
        """
        Cek apakah Gig sudah ada. Kalau belum, buat otomatis.
        Dipanggil di awal setiap shift Fiverr.
        Return True jika gig sudah ada atau berhasil dibuat.
        """
        if self.check_gig_exists():
            return True

        logger.info("[Fiverr] Belum ada Gig — membuat Gig Python Automation...")
        success = self.create_gig(template_index=0)
        if not success:
            logger.info("[Fiverr] Gig pertama gagal — coba template Web Scraping...")
            success = self.create_gig(template_index=1)

        if success:
            logger.info("[Fiverr] Gig berhasil dibuat. Buyer sekarang bisa menemukan dan order.")
        else:
            logger.warning("[Fiverr] Gig tidak bisa dibuat otomatis — buat manual di fiverr.com.")
        return success

    def search_and_offer_gigs(self) -> bool:
        """
        Di Fiverr, kita tidak apply ke job — kita menunggu order masuk ke Gig.
        Tapi kita bisa aktif di Fiverr Buyer Request (jika masih tersedia)
        atau optimasi Gig ranking dengan update deskripsi.
        Return True jika ada aktivitas yang dilakukan.
        """
        logger.info("[Fiverr] Memeriksa Buyer Requests (jika tersedia)...")
        try:
            self.browser.navigate("https://www.fiverr.com/users/selling/buyer_requests")
            page = self.browser.page
            page.wait_for_timeout(5000)

            # Cek apakah fitur Buyer Request masih ada
            requests_list = page.locator("div.request-row, article.buyer-request").all()
            if not requests_list:
                logger.info("[Fiverr] Buyer Request tidak tersedia. Gig sudah aktif menunggu order masuk.")
                return False

            sent_offers = 0
            for req in requests_list[:3]:
                try:
                    title_elem = req.locator("h3, p[class*='title']").first
                    title = title_elem.inner_text() if title_elem.is_visible() else ""

                    desc_elem = req.locator("p[class*='description'], div[class*='description']").first
                    desc = desc_elem.inner_text() if desc_elem.is_visible() else ""

                    # Buat penawaran via LLM
                    prompt = (
                        f"Buat offer singkat (maks 100 kata) untuk Fiverr Buyer Request berikut:\n"
                        f"Title: {title}\nDescription: {desc}\n"
                        "Tulis dalam bahasa profesional Inggris. Tekankan bahwa kamu bisa deliver dalam 24 jam."
                    )
                    offer_text = self.llm.generate_content(prompt)
                    if not offer_text:
                        continue

                    # Klik Send Offer
                    offer_btn = req.locator("button:has-text('Send Offer'), a:has-text('Send Offer')").first
                    if offer_btn.is_visible():
                        self.browser.human_click(offer_btn)
                        page.wait_for_timeout(2000)

                        offer_input = page.locator("textarea[placeholder*='offer'], div[contenteditable]").last
                        if offer_input.is_visible():
                            self.browser.human_type(offer_input, offer_text)
                            submit = page.locator("button:has-text('Submit'), button:has-text('Send')").first
                            self.browser.human_click(submit)
                            sent_offers += 1
                            page.wait_for_timeout(3000)

                except Exception as req_err:
                    logger.warning("[Fiverr] Error pada buyer request: %s", req_err)

            logger.info("[Fiverr] Sent %d offers dari buyer requests.", sent_offers)
            return sent_offers > 0

        except Exception as exc:
            logger.error("[Fiverr] Error di buyer requests: %s", exc)
            return False
