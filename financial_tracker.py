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
        logging.info(f"Financial Tracker: Logging new proposal for {platform}")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO finance_log (timestamp, platform, job_title, status, expected_revenue)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), platform, job_title, "PROPOSED", expected_revenue))
        conn.commit()
        conn.close()

    def update_job_status(self, job_title, new_status, actual_revenue=0.0):
        logging.info(f"Financial Tracker: Updating job '{job_title}' to {new_status}")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE finance_log
            SET status = ?, actual_revenue = ?
            WHERE job_title = ?
        ''', (new_status, actual_revenue, job_title))
        conn.commit()
        conn.close()

    def get_summary(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*), SUM(actual_revenue) FROM finance_log WHERE status = "PAID"')
        row = cursor.fetchone()
        conn.close()

        completed_jobs = row[0] if row[0] else 0
        total_revenue = row[1] if row[1] else 0.0
        return {"completed_jobs": completed_jobs, "total_revenue": total_revenue}
