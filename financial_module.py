import sqlite3
import logging

class FinancialModule:
    def __init__(self, db_path="agent_state.db"):
        self.db_path = db_path
        self._init_financial_table()

    def _init_financial_table(self):
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS financial_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'USD',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS account_balances (
                    platform TEXT PRIMARY KEY,
                    balance REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            logging.info("Financial Module initialized.")
        except sqlite3.Error as e:
            logging.error(f"Financial Module initialization error: {e}")

    def record_transaction(self, platform, transaction_type, amount, notes=""):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO financial_records (platform, transaction_type, amount, notes)
                VALUES (?, ?, ?, ?)
            ''', (platform, transaction_type, amount, notes))

            # Update balance
            cursor.execute('''
                INSERT INTO account_balances (platform, balance)
                VALUES (?, ?)
                ON CONFLICT(platform) DO UPDATE SET
                balance = balance + ?,
                last_updated = CURRENT_TIMESTAMP
            ''', (platform, amount, amount))

            conn.commit()
            conn.close()
            logging.info(f"Recorded transaction: {transaction_type} {amount} on {platform}")
        except sqlite3.Error as e:
            logging.error(f"Error recording transaction: {e}")

    def get_balance(self, platform):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT balance FROM account_balances WHERE platform = ?', (platform,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0.0
        except sqlite3.Error as e:
            logging.error(f"Error retrieving balance: {e}")
            return 0.0
