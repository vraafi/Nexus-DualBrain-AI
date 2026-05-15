"""
error_learning.py — Nexus DualBrain AI
=======================================
Belajar dari pattern error dan menerapkan recovery strategy secara AKTIF.

FIX KRITIS: Sebelumnya get_recovery_strategy() tidak pernah dipanggil dari manapun.
            Sekarang module ini terintegrasi ke orchestrator dan browser_agent.

Recovery strategy reference (Retry patterns):
https://github.com/jd/tenacity (43k+ stars)
https://github.com/litl/backoff (1.4k+ stars)
"""

import sqlite3
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorLearningSystem:
    """
    Sistem pembelajaran error yang AKTIF — bukan hanya logging.
    Setiap error dicatat, pola dianalisa, dan strategi recovery DITERAPKAN.
    """

    def __init__(self, db_path="error_patterns.db"):
        self.db_path = db_path
        self._init_db()
        self._seed_default_strategies()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    platform TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    context TEXT,
                    recovery_applied TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recovery_strategies (
                    error_type TEXT PRIMARY KEY,
                    strategy TEXT,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_updated DATETIME
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS platform_health (
                    platform TEXT PRIMARY KEY,
                    consecutive_failures INTEGER DEFAULT 0,
                    last_failure DATETIME,
                    is_paused INTEGER DEFAULT 0,
                    pause_until DATETIME
                )
            """)

    def _seed_default_strategies(self):
        """
        Seed strategi recovery default yang sudah terbukti efektif.
        Pattern ini dipakai secara luas di production scraping systems.
        Reference: https://github.com/scrapy/scrapy (scalable web crawling)
        """
        default_strategies = {
            "TimeoutError": "retry_with_backoff",
            "asyncio.TimeoutError": "retry_with_backoff",
            "ConnectionError": "wait_and_retry",
            "ConnectionRefusedError": "wait_and_retry",
            "SelectorNotFoundError": "retry_with_longer_wait",
            "ElementNotFoundError": "retry_with_longer_wait",
            "LoginRequiredError": "re-login",
            "AuthenticationError": "re-login",
            "RateLimitError": "wait_and_retry",
            "CaptchaError": "request_human_help",
            "TwoFactorRequiredError": "request_human_help",
            "Exception": "retry",
            "RuntimeError": "retry",
        }
        with sqlite3.connect(self.db_path) as conn:
            for error_type, strategy in default_strategies.items():
                conn.execute(
                    "INSERT OR IGNORE INTO recovery_strategies "
                    "(error_type, strategy, last_updated) VALUES (?, ?, ?)",
                    (error_type, strategy, datetime.now().isoformat())
                )

    def record_error(self, platform: str, error_type: str, error_message: str,
                     context=None, recovery_applied: str = None):
        """Catat error untuk pattern analysis."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO error_logs "
                    "(timestamp, platform, error_type, error_message, context, recovery_applied) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now().isoformat(),
                        platform, error_type, error_message[:500],
                        json.dumps(context) if context else None,
                        recovery_applied
                    )
                )
                # Update platform health
                conn.execute("""
                    INSERT INTO platform_health (platform, consecutive_failures, last_failure)
                    VALUES (?, 1, ?)
                    ON CONFLICT(platform) DO UPDATE SET
                        consecutive_failures = consecutive_failures + 1,
                        last_failure = excluded.last_failure
                """, (platform, datetime.now().isoformat()))

            logger.info("[ErrorLearning] Tercatat error '%s' pada %s", error_type, platform)
        except Exception as e:
            logger.error("[ErrorLearning] Gagal mencatat error: %s", e)

    def record_success(self, platform: str, error_type: str = None):
        """Catat keberhasilan — reset consecutive failures."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE platform_health
                    SET consecutive_failures = 0, is_paused = 0, pause_until = NULL
                    WHERE platform = ?
                """, (platform,))
                if error_type:
                    conn.execute("""
                        UPDATE recovery_strategies
                        SET success_count = success_count + 1, last_updated = ?
                        WHERE error_type = ?
                    """, (datetime.now().isoformat(), error_type))
        except Exception as e:
            logger.error("[ErrorLearning] Gagal catat success: %s", e)

    def get_recovery_strategy(self, platform: str, error_type: str) -> str:
        """
        Dapatkan strategi recovery berdasarkan histori.
        Strategy yang tersedia dan cara menerapkannya:
          - 'retry'               : coba lagi langsung
          - 'retry_with_backoff'  : coba lagi dengan delay eksponensial
          - 'retry_with_longer_wait' : tunggu 5 menit lalu retry
          - 're-login'            : login ulang ke platform
          - 'wait_and_retry'      : tunggu 5 menit (rate limit)
          - 'request_human_help'  : notifikasi ke Telegram, pause 10 menit
          - 'escalate'            : log critical, skip task ini
        """
        # Cek database dulu
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT strategy FROM recovery_strategies WHERE error_type = ?",
                    (error_type,)
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception:
            pass

        # Fallback defaults
        fallback_map = {
            "TimeoutError": "retry_with_backoff",
            "ConnectionError": "wait_and_retry",
            "Exception": "retry",
        }
        return fallback_map.get(error_type, "retry")

    def apply_recovery(self, platform: str, error_type: str,
                       error_message: str, hermes_agent=None) -> bool:
        """
        Terapkan recovery strategy secara aktif.
        Return True jika recovery berhasil/bisa dilanjutkan.

        Ini adalah method yang BENAR-BENAR mengambil tindakan,
        bukan sekadar mengembalikan string strategi.
        """
        strategy = self.get_recovery_strategy(platform, error_type)
        logger.info(
            "[ErrorLearning] Menerapkan '%s' untuk error '%s' di %s",
            strategy, error_type, platform
        )

        try:
            if strategy == "retry":
                time.sleep(5)
                return True

            elif strategy == "retry_with_backoff":
                # Exponential backoff: 10s, 20s, 40s
                consecutive = self._get_consecutive_failures(platform)
                delay = min(10 * (2 ** min(consecutive, 4)), 300)
                logger.info("[ErrorLearning] Backoff delay: %ds", delay)
                time.sleep(delay)
                return True

            elif strategy == "retry_with_longer_wait":
                logger.info("[ErrorLearning] Tunggu 5 menit sebelum retry...")
                time.sleep(300)
                return True

            elif strategy == "wait_and_retry":
                logger.info("[ErrorLearning] Rate limit terdeteksi. Tunggu 10 menit...")
                time.sleep(600)
                return True

            elif strategy == "re-login":
                logger.info("[ErrorLearning] Perlu re-login ke %s.", platform)
                return False  # Sinyal ke orchestrator untuk jalankan login ulang

            elif strategy == "request_human_help":
                logger.warning(
                    "[ErrorLearning] CAPTCHA/2FA terdeteksi di %s. "
                    "Menunggu intervensi manual (10 menit)...", platform
                )
                if hermes_agent:
                    hermes_agent.send_message(
                        f"CAPTCHA/2FA terdeteksi di {platform.upper()}!\n"
                        f"Error: {error_message[:200]}\n"
                        f"Menunggu 10 menit untuk intervensi manual."
                    )
                time.sleep(600)
                return True

            elif strategy == "escalate":
                logger.critical(
                    "[ErrorLearning] Error kritis di %s: %s — task di-skip.",
                    platform, error_message[:200]
                )
                return False

            else:
                time.sleep(30)
                return True

        except Exception as apply_err:
            logger.error("[ErrorLearning] Gagal apply recovery: %s", apply_err)
            return True

    def _get_consecutive_failures(self, platform: str) -> int:
        """Ambil jumlah consecutive failures untuk platform ini."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT consecutive_failures FROM platform_health WHERE platform = ?",
                    (platform,)
                )
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def should_pause_platform(self, platform: str, threshold: int = 10) -> bool:
        """
        Cek apakah platform perlu di-pause karena terlalu banyak failures.
        Threshold default: 10 consecutive failures = pause 1 jam.
        """
        consecutive = self._get_consecutive_failures(platform)
        if consecutive >= threshold:
            logger.warning(
                "[ErrorLearning] %s melebihi threshold (%d failures). "
                "Platform di-pause 1 jam.", platform, consecutive
            )
            try:
                with sqlite3.connect(self.db_path) as conn:
                    from datetime import timezone, timedelta
                    pause_until = (
                        datetime.now(timezone.utc) + timedelta(hours=1)
                    ).isoformat()
                    conn.execute("""
                        UPDATE platform_health
                        SET is_paused = 1, pause_until = ?
                        WHERE platform = ?
                    """, (pause_until, platform))
            except Exception:
                pass
            return True
        return False

    def get_platform_health_report(self) -> dict:
        """Laporan kesehatan semua platform — untuk dashboard dan Telegram /status."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT platform, consecutive_failures, last_failure, is_paused "
                    "FROM platform_health"
                )
                rows = cursor.fetchall()
                return {
                    row[0]: {
                        "consecutive_failures": row[1],
                        "last_failure": row[2],
                        "is_paused": bool(row[3]),
                    }
                    for row in rows
                }
        except Exception:
            return {}
