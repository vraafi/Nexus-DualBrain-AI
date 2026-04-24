import sqlite3
import json
import os

DB_PATH = "agent_state.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_module INTEGER DEFAULT 1,
            product_data TEXT DEFAULT '{}',
            video_paths TEXT DEFAULT '[]',
            status TEXT DEFAULT 'running',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Insert initial state if empty
    cursor.execute("SELECT COUNT(*) FROM state")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO state (current_module, status) VALUES (1, 'running')")
    conn.commit()
    conn.close()

def get_state():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT current_module, product_data, video_paths, status FROM state ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "current_module": row[0],
            "product_data": json.loads(row[1]) if row[1] else {},
            "video_paths": json.loads(row[2]) if row[2] else [],
            "status": row[3]
        }
    return None

def update_state(current_module, product_data=None, video_paths=None, status="running"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get current values to not overwrite with nulls if not provided
    current_state = get_state()
    if current_state:
        if product_data is None:
            product_data = current_state.get("product_data", {})
        if video_paths is None:
            video_paths = current_state.get("video_paths", [])

    cursor.execute("""
        UPDATE state
        SET current_module = ?, product_data = ?, video_paths = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = (SELECT MAX(id) FROM state)
    """, (current_module, json.dumps(product_data), json.dumps(video_paths), status))

    conn.commit()
    conn.close()

def reset_state():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE state SET current_module = 1, product_data = '{}', video_paths = '[]', status = 'running' WHERE id = (SELECT MAX(id) FROM state)")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(get_state())
