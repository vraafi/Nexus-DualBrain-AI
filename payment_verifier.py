"""
payment_verifier.py — Nexus DualBrain AI
=========================================
Modul untuk verifikasi pembayaran yang masuk dari semua platform.

Sebelumnya FinancialTracker hanya log "PROPOSED" dan "DELIVERED" tapi TIDAK PERNAH
update ke status "PAID". Akibatnya /earnings command selalu menunjukkan $0 revenue.

FIX: PaymentVerifier secara aktif memeriksa halaman earnings di setiap platform
     dan update status job menjadi "PAID" ketika uang sudah di-release.

Reference payment verification pattern:
https://github.com/paymentwall/paymentwall-python (official payment library)
https://support.upwork.com/hc/en-us/articles/211062608 (Upwork payment flow docs)
"""

import logging
import json
import re
import time
from financial_tracker import FinancialTracker

logger = logging.getLogger(__name__)


class PaymentVerifier:
    """
    Verifikasi pembayaran yang masuk dari semua platform.
    Jalankan ini setiap 24 jam untuk update status DELIVERED -> PAID.
    """

    def __init__(self, browser_agent, llm_client, finance_tracker: FinancialTracker = None):
        self.browser = browser_agent
        self.llm = llm_client
        self.finance = finance_tracker or FinancialTracker()
        self.logger = logging.getLogger(__name__)

    def verify_upwork_payments(self) -> int:
        """
        Cek halaman Upwork Transactions untuk melihat pembayaran yang sudah masuk.
        Return jumlah pembayaran baru yang terdeteksi.
        """
        self.logger.info("[PaymentVerifier] Mengecek Upwork transactions...")

        result = self.browser.execute_task(
            "Buka https://www.upwork.com/nx/payments/reports/overview. "
            "Atau buka https://www.upwork.com/ab/payments/reports/billing-history. "
            "List semua transaksi payment yang berhasil dalam 30 hari terakhir. "
            "Return JSON: [{title, amount, date, status}, ...]",
            max_steps=8
        )

        paid_count = 0
        try:
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                transactions = json.loads(match.group(0))
                for tx in transactions:
                    if tx.get("status", "").lower() in ["paid", "released", "completed"]:
                        title = tx.get("title", "")
                        amount = float(tx.get("amount", 0))
                        if title and amount > 0:
                            self.finance.update_job_status(title, "PAID", amount)
                            self.logger.info(
                                "[PaymentVerifier] Upwork PAID: '%s' — $%.2f", title, amount
                            )
                            paid_count += 1
        except Exception as e:
            self.logger.error("[PaymentVerifier] Gagal parse Upwork transactions: %s", e)

        return paid_count

    def verify_fiverr_payments(self) -> int:
        """
        Cek halaman Fiverr Revenue untuk melihat order yang sudah cleared.
        Return jumlah pembayaran baru yang terdeteksi.
        """
        self.logger.info("[PaymentVerifier] Mengecek Fiverr revenue...")

        result = self.browser.execute_task(
            "Buka https://www.fiverr.com/users/selling/analytics. "
            "Atau buka halaman 'Revenues' atau 'Earnings' di Fiverr seller dashboard. "
            "List order yang statusnya 'Cleared' atau sudah dibayarkan. "
            "Return JSON: [{order_id, title, amount, status}, ...]",
            max_steps=8
        )

        paid_count = 0
        try:
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                transactions = json.loads(match.group(0))
                for tx in transactions:
                    if tx.get("status", "").lower() in ["cleared", "completed", "paid"]:
                        title = tx.get("title", tx.get("order_id", "Fiverr Order"))
                        amount = float(tx.get("amount", 0))
                        if amount > 0:
                            self.finance.update_job_status(title, "PAID", amount)
                            self.logger.info(
                                "[PaymentVerifier] Fiverr CLEARED: '%s' — $%.2f", title, amount
                            )
                            paid_count += 1
        except Exception as e:
            self.logger.error("[PaymentVerifier] Gagal parse Fiverr revenues: %s", e)

        return paid_count

    def verify_freelancer_payments(self) -> int:
        """
        Cek halaman Freelancer.com Transactions untuk milestone yang sudah di-release.
        Return jumlah pembayaran baru yang terdeteksi.
        """
        self.logger.info("[PaymentVerifier] Mengecek Freelancer.com transactions...")

        result = self.browser.execute_task(
            "Buka https://www.freelancer.com/users/settings.php?frm=payment_history. "
            "Atau navigasi ke Financial > Payment History di Freelancer.com. "
            "List semua pembayaran yang sudah diterima dalam 30 hari terakhir. "
            "Return JSON: [{project_title, amount, status, date}, ...]",
            max_steps=8
        )

        paid_count = 0
        try:
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                transactions = json.loads(match.group(0))
                for tx in transactions:
                    if tx.get("status", "").lower() in ["paid", "released", "completed", "cleared"]:
                        title = tx.get("project_title", "Freelancer Project")
                        amount = float(tx.get("amount", 0))
                        if amount > 0:
                            self.finance.update_job_status(title, "PAID", amount)
                            self.logger.info(
                                "[PaymentVerifier] Freelancer PAID: '%s' — $%.2f", title, amount
                            )
                            paid_count += 1
        except Exception as e:
            self.logger.error("[PaymentVerifier] Gagal parse Freelancer transactions: %s", e)

        return paid_count

    def run_full_verification(self) -> dict:
        """
        Jalankan verifikasi pembayaran untuk semua platform.
        Dipanggil sekali per hari dari main.py.

        Return dict dengan summary pembayaran baru yang terdeteksi.
        """
        self.logger.info("[PaymentVerifier] Memulai verifikasi pembayaran semua platform...")

        results = {
            "upwork": 0,
            "fiverr": 0,
            "freelancer": 0,
            "total_new_payments": 0,
        }

        try:
            results["upwork"] = self.verify_upwork_payments()
            time.sleep(5)
            results["fiverr"] = self.verify_fiverr_payments()
            time.sleep(5)
            results["freelancer"] = self.verify_freelancer_payments()
        except Exception as e:
            self.logger.error("[PaymentVerifier] Error saat verifikasi: %s", e)

        results["total_new_payments"] = (
            results["upwork"] + results["fiverr"] + results["freelancer"]
        )

        summary = self.finance.get_summary()
        self.logger.info(
            "[PaymentVerifier] Verifikasi selesai. Pembayaran baru: %d | "
            "Total revenue: $%.2f | Pending: $%.2f",
            results["total_new_payments"],
            summary.get("total_revenue", 0),
            summary.get("pending_revenue", 0),
        )

        return results
