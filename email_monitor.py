"""
email_monitor.py
================
Monitor inbox email secara periodik menggunakan IMAP.
Mendeteksi notifikasi pesanan masuk dari Upwork, Fiverr, dan Freelancer.
Berjalan di background thread terpisah agar tidak menghentikan workflow utama.
"""

import imaplib
import email
import email.message
import logging
import threading
import time
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from email.header import decode_header

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

# Interval cek email dalam detik
EMAIL_CHECK_INTERVAL = int(os.environ.get("EMAIL_CHECK_INTERVAL", 300))  # default 5 menit

# Penanda email yang sudah diproses (pakai Message-ID)
_processed_ids: set = set()


@dataclass
class IncomingOrder:
    platform: str           # "upwork" | "fiverr" | "freelancer"
    order_id: str           # Message-ID email sebagai unique key
    client_name: str
    subject: str
    description: str
    received_at: datetime = field(default_factory=lambda: datetime.now(WIB))
    is_handled: bool = False


# ─────────────────────────────────────────────
# Helper: decode email header (bisa encoded)
# ─────────────────────────────────────────────

def _decode_header_str(raw_header: str) -> str:
    parts = decode_header(raw_header or "")
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _get_body(msg: email.message.Message) -> str:
    """Ekstrak teks biasa dari email (text/plain)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                try:
                    body += part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    pass
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
    return body.strip()


# ─────────────────────────────────────────────
# Deteksi platform dari alamat pengirim / subject
# ─────────────────────────────────────────────

PLATFORM_SIGNATURES = {
    "upwork": [
        "upwork.com",
        "no-reply@upwork.com",
        "notification@upwork.com",
        "donotreply@upwork.com",
    ],
    "fiverr": [
        "fiverr.com",
        "no-reply@fiverr.com",
        "notifications@fiverr.com",
    ],
    "freelancer": [
        "freelancer.com",
        "no-reply@freelancer.com",
        "notifications@freelancer.com",
    ],
}

ORDER_KEYWORDS = [
    "new order", "order received", "new message", "hired you",
    "contract", "offer", "pesanan baru", "pesan baru",
    "job invitation", "invited you", "revision", "delivery"
]


def _detect_platform(from_addr: str, subject: str) -> Optional[str]:
    combined = (from_addr + " " + subject).lower()
    for platform, signatures in PLATFORM_SIGNATURES.items():
        if any(sig in combined for sig in signatures):
            return platform
    return None


def _is_order_notification(subject: str, body: str) -> bool:
    text = (subject + " " + body).lower()
    return any(kw in text for kw in ORDER_KEYWORDS)


# ─────────────────────────────────────────────
# IMAP Reader
# ─────────────────────────────────────────────

class IMAPReader:
    """
    Membaca email dari akun Gmail/IMAP dan mengembalikan daftar IncomingOrder baru.
    Mendukung Gmail (imap.gmail.com) dan IMAP generik.
    """

    def __init__(self):
        self.host = os.environ.get("EMAIL_IMAP_HOST", "imap.gmail.com")
        self.port = int(os.environ.get("EMAIL_IMAP_PORT", 993))
        self.user = os.environ.get("EMAIL_ADDRESS", "")
        self.password = os.environ.get("EMAIL_APP_PASSWORD", "")  # Gunakan App Password untuk Gmail

    def _connect(self) -> Optional[imaplib.IMAP4_SSL]:
        if not self.user or not self.password:
            logger.warning("[IMAP] EMAIL_ADDRESS atau EMAIL_APP_PASSWORD tidak di-set. Email monitoring non-aktif.")
            return None
        try:
            conn = imaplib.IMAP4_SSL(self.host, self.port)
            conn.login(self.user, self.password)
            return conn
        except Exception as exc:
            logger.error("[IMAP] Gagal connect: %s", exc)
            return None

    def fetch_new_orders(self) -> list[IncomingOrder]:
        """Ambil email UNSEEN dari INBOX dan kembalikan hanya yang merupakan notifikasi order."""
        orders = []
        conn = self._connect()
        if not conn:
            return orders

        try:
            conn.select("INBOX")
            _, data = conn.search(None, "UNSEEN")
            uid_list = data[0].split()

            for uid in uid_list:
                try:
                    _, msg_data = conn.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    msg_id = msg.get("Message-ID", uid.decode())
                    if msg_id in _processed_ids:
                        continue

                    from_addr = _decode_header_str(msg.get("From", ""))
                    subject   = _decode_header_str(msg.get("Subject", ""))
                    body      = _get_body(msg)

                    platform = _detect_platform(from_addr, subject)
                    if not platform:
                        continue  # bukan dari 3 platform kita

                    if not _is_order_notification(subject, body):
                        continue  # email biasa (newsletter, dll), skip

                    # Ekstrak nama klien (dari alamat pengirim)
                    client_name = from_addr.split("<")[0].strip().strip('"') or from_addr

                    order = IncomingOrder(
                        platform=platform,
                        order_id=msg_id,
                        client_name=client_name,
                        subject=subject,
                        description=body[:500],  # ambil 500 karakter pertama sebagai konteks
                    )
                    orders.append(order)
                    _processed_ids.add(msg_id)
                    logger.info("[IMAP] 📬 Order baru dari %s | Platform: %s | Subject: %s",
                                client_name, platform.upper(), subject)

                except Exception as msg_err:
                    logger.warning("[IMAP] Gagal parse satu email: %s", msg_err)

        except Exception as exc:
            logger.error("[IMAP] Gagal fetch email: %s", exc)
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        return orders


# ─────────────────────────────────────────────
# EmailMonitor — thread background
# ─────────────────────────────────────────────

class EmailMonitor:
    """
    Berjalan di thread daemon terpisah.
    Setiap EMAIL_CHECK_INTERVAL detik, cek inbox via IMAP.
    Order baru ditambahkan ke priority queue (thread-safe).
    """

    def __init__(self):
        self._queue: list[IncomingOrder] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._reader = IMAPReader()

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="EmailMonitor"
        )
        self._thread.start()
        logger.info("[EmailMonitor] ✅ Dimulai — cek setiap %d menit.", EMAIL_CHECK_INTERVAL // 60)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
        logger.info("[EmailMonitor] Dihentikan.")

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                new_orders = self._reader.fetch_new_orders()
                if new_orders:
                    with self._lock:
                        self._queue.extend(new_orders)
                    logger.info("[EmailMonitor] ⚡ %d pesanan baru masuk ke priority queue.", len(new_orders))
            except Exception as exc:
                logger.warning("[EmailMonitor] Error saat cek email: %s", exc)
            self._stop_event.wait(timeout=EMAIL_CHECK_INTERVAL)

    # ── Public API ──────────────────────────────

    def has_priority_orders(self) -> bool:
        with self._lock:
            return any(not o.is_handled for o in self._queue)

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for o in self._queue if not o.is_handled)

    def pop_next_order(self) -> Optional[IncomingOrder]:
        """Ambil pesanan berikutnya yang belum ditangani (FIFO)."""
        with self._lock:
            for order in self._queue:
                if not order.is_handled:
                    order.is_handled = True
                    return order
        return None

    def inject_test_order(self, platform: str, subject: str, description: str):
        """Untuk testing — inject order dummy ke queue."""
        order = IncomingOrder(
            platform=platform,
            order_id=f"test_{int(time.time())}",
            client_name="Test Client",
            subject=subject,
            description=description,
        )
        with self._lock:
            self._queue.append(order)
        logger.info("[EmailMonitor] 🧪 Test order injected untuk platform: %s", platform)
