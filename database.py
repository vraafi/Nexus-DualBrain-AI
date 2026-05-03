import sqlite3
import json
import os

DB_NAME = "agent_state.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL,
            current_step TEXT,
            data TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_state(task_id, status, current_step, data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data_str = json.dumps(data) if data else "{}"

    cursor.execute('''
        INSERT INTO task_state (task_id, status, current_step, data)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            status = excluded.status,
            current_step = excluded.current_step,
            data = excluded.data
    ''', (task_id, status, current_step, data_str))
    conn.commit()
    conn.close()

def load_state(task_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT status, current_step, data FROM task_state WHERE task_id = ?', (task_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "status": row[0],
            "current_step": row[1],
            "data": json.loads(row[2])
        }
    return None

if __name__ == "__main__":
    init_db()
    print("Database ready.")
