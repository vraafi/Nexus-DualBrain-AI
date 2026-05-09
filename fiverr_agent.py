"""
fiverr_agent.py
===============
Agent untuk platform Fiverr: manage gig orders yang masuk,
reply ke buyer, dan deliver hasil kerja.
Berbeda dengan Upwork (kita apply ke job), di Fiverr kita
menunggu order masuk ke Gig kita, lalu memprosesnya.
"""

import logging
import json
import time

logger = logging.getLogger(__name__)


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
