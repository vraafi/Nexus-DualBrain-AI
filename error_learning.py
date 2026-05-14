import sqlite3
import json
import logging
from datetime import datetime

class ErrorLearningSystem:
    """Belajar dari pattern error untuk recovery yang lebih baik"""
    
    def __init__(self, db_path="error_patterns.db"):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    platform TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    context TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recovery_strategies (
                    error_type TEXT PRIMARY KEY,
                    strategy TEXT
                )
            """)
        
    def record_error(self, platform, error_type, error_message, context=None):
        """Catat error untuk pattern analysis"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO error_logs (timestamp, platform, error_type, error_message, context) VALUES (?, ?, ?, ?, ?)",
                    (datetime.now(), platform, error_type, error_message, json.dumps(context) if context else None)
                )
            logging.info(f"[ErrorLearning] Tercatat error {error_type} pada {platform}")
        except Exception as e:
            logging.error(f"Gagal mencatat error: {e}")
            
    def get_recovery_strategy(self, platform, error_type):
        """Dapatkan strategi recovery berdasarkan histori"""
        # Default strategies
        strategies = {
            "TimeoutError": "retry",
            "SelectorNotFoundError": "use_backup_selector",
            "LoginRequiredError": "re-login",
            "RateLimitError": "wait_and_retry"
        }
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT strategy FROM recovery_strategies WHERE error_type = ?", (error_type,))
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception:
            pass
            
        return strategies.get(error_type, "escalate")
