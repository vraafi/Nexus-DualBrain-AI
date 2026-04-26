import sqlite3
import logging

class DatabaseManager:
    def __init__(self, db_path="agent_state.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            ''')
            self.conn.commit()
            logging.info(f"Database initialized at {self.db_path}")
        except sqlite3.Error as e:
            logging.error(f"Database initialization error: {e}")

    def update_task_state(self, task_name, status, details=""):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO task_state (task_name, status, details)
                VALUES (?, ?, ?)
                ON CONFLICT(task_name) DO UPDATE SET
                status=excluded.status,
                last_updated=CURRENT_TIMESTAMP,
                details=excluded.details
            ''', (task_name, status, details))
            self.conn.commit()
            logging.info(f"Task '{task_name}' updated to status '{status}'.")
        except sqlite3.Error as e:
            logging.error(f"Error updating task state: {e}")

    def get_task_state(self, task_name):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT status, details FROM task_state WHERE task_name = ?', (task_name,))
            result = cursor.fetchone()
            if result:
                return {"status": result[0], "details": result[1]}
            return None
        except sqlite3.Error as e:
            logging.error(f"Error retrieving task state: {e}")
            return None

    def close(self):
        if self.conn:
            self.conn.close()
            logging.info("Database connection closed.")
