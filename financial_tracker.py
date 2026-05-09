"""
financial_tracker.py — Pelacak keuangan untuk Nexus DualBrain AI
Fix: Tambah total_proposals ke get_summary() untuk OpenClaw /earnings command
"""

import sqlite3
import os
import logging
from datetime import datetime

DB_NAME = "agent_state.db"


class FinancialTracker:
    def __init__(self):
        self._init_financial_tables()

    def _init_financial_tables(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS finance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                platform TEXT NOT NULL,
                job_title TEXT NOT NULL,
                status TEXT NOT NULL,
                expected_revenue REAL DEFAULT 0.0,
                actual_revenue REAL DEFAULT 0.0,
                notes TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def log_proposal(self, platform, job_title, expected_revenue=0.0):
        logging.info(f"[Finance] Proposal baru di {platform}: {job_title} (est. ${expected_revenue})")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO finance_log (timestamp, platform, job_title, status, expected_revenue)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), platform, job_title, "PROPOSED", expected_revenue))
        conn.commit()
        conn.close()

    def update_job_status(self, job_title, new_status, actual_revenue=0.0):
        logging.info(f"[Finance] Update job '{job_title}' → {new_status} (revenue: ${actual_revenue})")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE finance_log
            SET status = ?, actual_revenue = ?
            WHERE job_title = ?
        ''', (new_status, actual_revenue, job_title))
        conn.commit()
        conn.close()

    def get_summary(self) -> dict:
        """Ringkasan keuangan untuk OpenClaw /earnings command."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Job yang sudah dibayar
        cursor.execute(
            'SELECT COUNT(*), COALESCE(SUM(actual_revenue), 0) FROM finance_log WHERE status = "PAID"'
        )
        paid_row = cursor.fetchone()

        # Job yang sudah dideliver (menunggu pembayaran)
        cursor.execute(
            'SELECT COUNT(*), COALESCE(SUM(actual_revenue), 0) FROM finance_log WHERE status = "DELIVERED"'
        )
        delivered_row = cursor.fetchone()

        # Total proposal yang pernah dikirim
        cursor.execute('SELECT COUNT(*) FROM finance_log WHERE status = "PROPOSED"')
        proposal_row = cursor.fetchone()

        conn.close()

        return {
            "completed_jobs": paid_row[0] or 0,
            "total_revenue": paid_row[1] or 0.0,
            "pending_revenue": delivered_row[1] or 0.0,
            "delivered_jobs": delivered_row[0] or 0,
            "total_proposals": proposal_row[0] or 0,
        }

    def get_recent_jobs(self, limit: int = 10) -> list:
        """Ambil job terbaru untuk ditampilkan di dashboard."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT platform, job_title, status, actual_revenue, timestamp
            FROM finance_log
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "platform": r[0],
                "title": r[1],
                "status": r[2],
                "revenue": r[3],
                "timestamp": r[4],
            }
            for r in rows
        ]
