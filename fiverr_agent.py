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

logger = logging.getLogger(__name__)

# Template gig yang akan di-generate oleh LLM
GIG_TEMPLATES = [
    {
        "niche": "python_automation",
        "title": "I will build custom Python automation scripts and bots",
        "category_hint": "Programming & Tech",
        "subcategory_hint": "Scripts & Utilities",
        "tags": ["python", "automation", "script", "bot", "web scraping"],
        "basic":    {"price": 15, "days": 1, "revisions": 1, "label": "Basic Script",    "desc": "Simple automation script, up to 50 lines, 1 feature."},
        "standard": {"price": 35, "days": 2, "revisions": 2, "label": "Standard Bot",   "desc": "Full automation bot with error handling and logging."},
        "premium":  {"price": 75, "days": 3, "revisions": 999, "label": "Pro Solution", "desc": "Production-ready solution with tests and documentation."},
    },
    {
        "niche": "web_scraping",
        "title": "I will scrape any website and deliver clean structured data",
        "category_hint": "Programming & Tech",
        "subcategory_hint": "Data Processing",
        "tags": ["web scraping", "python", "data extraction", "beautifulsoup", "selenium"],
        "basic":    {"price": 20, "days": 1, "revisions": 1, "label": "Basic Scraper",  "desc": "Scrape one page, up to 500 records, delivered as CSV."},
        "standard": {"price": 45, "days": 2, "revisions": 2, "label": "Multi-page",     "desc": "Multi-page scraper with pagination, JSON + CSV output."},
        "premium":  {"price": 90, "days": 3, "revisions": 999, "label": "Full Pipeline","desc": "Full pipeline: scrape + clean + schedule + delivery."},
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

    def create_gig(self, template_index: int = 0) -> bool:
        """
        Buat Gig baru di Fiverr secara otomatis menggunakan template + LLM.
        template_index: 0 = python automation, 1 = web scraping
        Return True jika berhasil membuat gig.
        """
        template = GIG_TEMPLATES[template_index % len(GIG_TEMPLATES)]
        logger.info("[Fiverr] Membuat Gig baru: '%s' ...", template["title"])

        # Generate deskripsi panjang dengan LLM
        prompt = (
            f"Write a professional and persuasive Fiverr gig description for:\n"
            f"Title: {template['title']}\n"
            f"Target buyer: small businesses and startups needing Python development.\n\n"
            "Requirements:\n"
            "- 150-200 words\n"
            "- Start with a strong hook\n"
            "- List 4-5 bullet points of what buyer gets\n"
            "- End with a clear call to action\n"
            "- Professional English, no emojis\n"
            "Output ONLY the gig description text, no markdown or quotes."
        )
        description = self.llm.generate_content(prompt)
        if not description:
            description = (
                f"Looking for a reliable Python developer? You've found the right gig!\n\n"
                f"I specialize in building clean, efficient, and production-ready Python solutions "
                f"tailored to your exact needs.\n\n"
                f"What you'll get:\n"
                f"- Custom Python scripts and automation tools\n"
                f"- Clean, well-commented code with error handling\n"
                f"- Fast delivery with revisions included\n"
                f"- Full documentation and support\n\n"
                f"Order now and let's build something great together!"
            )

        try:
            page = self.browser.page
            self.browser.navigate("https://www.fiverr.com/gigs/new")
            page.wait_for_timeout(5000)

            # ── Step 1: Judul Gig ──────────────────────────────────────────
            title_input = page.locator("input[name='title'], input[placeholder*='title'], input[id*='title']").first
            if title_input.is_visible(timeout=5000):
                self.browser.human_type(title_input, template["title"])
                page.wait_for_timeout(1000)
            else:
                logger.warning("[Fiverr] Input judul gig tidak ditemukan.")
                return False

            # ── Step 2: Kategori ───────────────────────────────────────────
            category_btn = page.locator("select[name='category'], div[class*='category'] button, div[class*='category-select']").first
            if category_btn.is_visible(timeout=3000):
                self.browser.human_click(category_btn)
                page.wait_for_timeout(1000)
                # Pilih Programming & Tech
                prog_option = page.locator(f"option:has-text('Programming'), li:has-text('Programming'), div:has-text('Programming & Tech')").first
                if prog_option.is_visible(timeout=3000):
                    self.browser.human_click(prog_option)
                    page.wait_for_timeout(1000)

            # ── Step 3: Tags ───────────────────────────────────────────────
            tag_input = page.locator("input[placeholder*='tag'], input[name*='tag'], div[class*='tags'] input").first
            if tag_input.is_visible(timeout=3000):
                for tag in template["tags"][:5]:
                    self.browser.human_type(tag_input, tag)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(500)

            # ── Step 4: Lanjut ke halaman berikutnya ──────────────────────
            next_btn = page.locator("button:has-text('Next'), button:has-text('Save & Continue')").first
            if next_btn.is_visible(timeout=5000):
                self.browser.human_click(next_btn)
                page.wait_for_timeout(4000)

            # ── Step 5: Deskripsi ──────────────────────────────────────────
            desc_box = page.locator("div[contenteditable='true'], textarea[name='description'], div[class*='description'] textarea").first
            if desc_box.is_visible(timeout=5000):
                self.browser.human_type(desc_box, description)
                page.wait_for_timeout(1000)

            # ── Step 6: Paket Harga (Basic) ────────────────────────────────
            for pkg_key, pkg_data in [("basic", template["basic"]), ("standard", template["standard"]), ("premium", template["premium"])]:
                try:
                    # Harga
                    price_input = page.locator(f"input[name*='{pkg_key}'][name*='price'], input[data-package='{pkg_key}'][name*='price']").first
                    if price_input.is_visible(timeout=3000):
                        price_input.triple_click()
                        self.browser.human_type(price_input, str(pkg_data["price"]))
                        page.wait_for_timeout(500)

                    # Delivery time
                    delivery_input = page.locator(f"select[name*='{pkg_key}'][name*='delivery'], input[data-package='{pkg_key}'][name*='delivery']").first
                    if delivery_input.is_visible(timeout=3000):
                        delivery_input.select_option(str(pkg_data["days"]))
                        page.wait_for_timeout(500)
                except Exception as pkg_err:
                    logger.warning("[Fiverr] Gagal isi paket %s: %s", pkg_key, pkg_err)

            # ── Step 7: Lanjut ke publish ──────────────────────────────────
            next_btn2 = page.locator("button:has-text('Next'), button:has-text('Save & Continue')").first
            if next_btn2.is_visible(timeout=5000):
                self.browser.human_click(next_btn2)
                page.wait_for_timeout(4000)

            # ── Step 8: Publish Gig ────────────────────────────────────────
            publish_btn = page.locator("button:has-text('Publish'), button:has-text('Save & Publish')").first
            if publish_btn.is_visible(timeout=8000):
                self.browser.human_click(publish_btn)
                page.wait_for_timeout(5000)
                logger.info("[Fiverr] ✅ Gig '%s' berhasil dipublikasikan!", template["title"])
                return True
            else:
                logger.warning("[Fiverr] Tombol Publish tidak ditemukan — mungkin perlu review manual.")
                return False

        except Exception as exc:
            logger.error("[Fiverr] Gagal membuat Gig: %s", exc)
            return False

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
            logger.info("[Fiverr] ✅ Gig berhasil dibuat. Buyer sekarang bisa menemukan dan order.")
        else:
            logger.warning("[Fiverr] ⚠️ Gig tidak bisa dibuat otomatis — buat manual di fiverr.com.")
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
