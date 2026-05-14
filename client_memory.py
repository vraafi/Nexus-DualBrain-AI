import sqlite3
import os
import logging
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
MEMORY_BASE = os.path.expanduser("~/.hermes/memory/clients")
DB_PATH = os.path.join(MEMORY_BASE, "clients_state.db")

class ClientMemory:
    """
    Sistem memori canggih diadaptasi dari Hermes Agent (FTS5 SQLite).
    Menggantikan folder file .md lama yang rapuh dan lambat.
    """
    def __init__(self):
        os.makedirs(MEMORY_BASE, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        # Timeout dan WAL (Write-Ahead Logging) mode diaktifkan persis seperti Hermes
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass # Fallback jika filesystem tidak dukung WAL (WSL1)
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Tabel utama Klien
            cursor.executescript('''
            CREATE TABLE IF NOT EXISTS clients (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                username TEXT NOT NULL,
                name TEXT,
                rating TEXT,
                location TEXT,
                language TEXT,
                status TEXT,
                active_job TEXT,
                last_contact TEXT
            );
            
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT REFERENCES clients(id),
                date TEXT,
                title TEXT,
                budget REAL,
                status TEXT,
                revenue REAL
            );
            
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT REFERENCES clients(id),
                type TEXT, -- 'negotiation', 'preference', dll
                date TEXT,
                content TEXT
            );
            ''')
            
            # Sistem FTS5 (Full-Text Search) persis seperti hermes_state.py
            try:
                cursor.execute("SELECT * FROM notes_fts LIMIT 0")
            except sqlite3.OperationalError:
                cursor.executescript('''
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    content, client_id UNINDEXED
                );
                
                CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
                    INSERT INTO notes_fts(rowid, content, client_id) VALUES (new.id, new.content, new.client_id);
                END;
                
                CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
                    DELETE FROM notes_fts WHERE rowid = old.id;
                END;
                
                CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE ON notes BEGIN
                    DELETE FROM notes_fts WHERE rowid = old.id;
                    INSERT INTO notes_fts(rowid, content, client_id) VALUES (new.id, new.content, new.client_id);
                END;
                ''')
            conn.commit()

    def _get_client_id(self, platform: str, username: str) -> str:
        return f"{platform.lower()}:{username}"

    def create_if_not_exists(self, platform: str, username: str,
                              name: str = "", rating: str = "N/A",
                              location: str = "Unknown", language: str = "English") -> str:
        client_id = self._get_client_id(platform, username)
        now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
        with self._get_conn() as conn:
            conn.execute('''
            INSERT OR IGNORE INTO clients (id, platform, username, name, rating, location, language, status, active_job, last_contact)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PROSPECT', 'None', ?)
            ''', (client_id, platform, username, name or username, rating, location, language, now))
            conn.commit()
        return "Created"

    def add_job(self, platform: str, username: str,
                job_title: str, budget: float, status: str, revenue: float = 0.0):
        self.create_if_not_exists(platform, username)
        client_id = self._get_client_id(platform, username)
        now = datetime.now(WIB).strftime("%Y-%m-%d")
        last_contact = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
        with self._get_conn() as conn:
            conn.execute('INSERT INTO jobs (client_id, date, title, budget, status, revenue) VALUES (?, ?, ?, ?, ?, ?)',
                         (client_id, now, job_title, budget, status, revenue))
            conn.execute('UPDATE clients SET last_contact = ? WHERE id = ?', (last_contact, client_id))
            conn.commit()
        logging.info(f"[Memory] Job ditambahkan ke memori {platform}/{username}: {job_title}")

    def add_negotiation_note(self, platform: str, username: str, note: str):
        self.create_if_not_exists(platform, username)
        client_id = self._get_client_id(platform, username)
        now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M")
        last_contact = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
        with self._get_conn() as conn:
            conn.execute('INSERT INTO notes (client_id, type, date, content) VALUES (?, "negotiation", ?, ?)',
                         (client_id, now, note))
            conn.execute('UPDATE clients SET last_contact = ? WHERE id = ?', (last_contact, client_id))
            conn.commit()

    def update_status(self, platform: str, username: str, status: str, active_job: str = ""):
        self.create_if_not_exists(platform, username)
        client_id = self._get_client_id(platform, username)
        last_contact = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
        with self._get_conn() as conn:
            if active_job:
                conn.execute('UPDATE clients SET status = ?, active_job = ?, last_contact = ? WHERE id = ?',
                             (status, active_job, last_contact, client_id))
            else:
                conn.execute('UPDATE clients SET status = ?, last_contact = ? WHERE id = ?',
                             (status, last_contact, client_id))
            conn.commit()

    def add_preference(self, platform: str, username: str, preference: str):
        self.create_if_not_exists(platform, username)
        client_id = self._get_client_id(platform, username)
        now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M")
        with self._get_conn() as conn:
            conn.execute('INSERT INTO notes (client_id, type, date, content) VALUES (?, "preference", ?, ?)',
                         (client_id, now, preference))
            conn.commit()

    def search_memory_fts5(self, query: str) -> list:
        """Fitur eksklusif dari Hermes: Full-Text Search secepat kilat."""
        try:
            with self._get_conn() as conn:
                # MATCH query syntax untuk FTS5
                safe_query = query.replace('"', '""')
                results = conn.execute(f'''
                SELECT client_id, content, snippet(notes_fts, -1, ">>", "<<", "...", 64) as snippet
                FROM notes_fts
                WHERE content MATCH '"{safe_query}"*'
                ORDER BY rank LIMIT 10
                ''').fetchall()
                return [dict(r) for r in results]
        except Exception as e:
            logging.error(f"[FTS5] Pencarian error: {e}")
            return []

    def get_context_for_llm(self, platform: str, username: str) -> str:
        """Generate ulang format markdown saat runtime (tidak disimpan sbg markdown)."""
        client_id = self._get_client_id(platform, username)
        with self._get_conn() as conn:
            client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
            if not client:
                return f"Klien baru dari {platform}. Belum ada riwayat."
                
            prefs = conn.execute('SELECT content FROM notes WHERE client_id = ? AND type="preference"', (client_id,)).fetchall()
            negos = conn.execute('SELECT date, content FROM notes WHERE client_id = ? AND type="negotiation" ORDER BY id DESC LIMIT 5', (client_id,)).fetchall()
            
            sections = []
            if prefs:
                sections.append("## Preferensi & Catatan\n" + "\n".join(f"- {p['content']}" for p in prefs))
            if negos:
                sections.append("## Riwayat Negosiasi Terbaru\n" + "\n".join(f"- {n['date']}: {n['content']}" for n in negos))
                
            sections.append(f"## Status Saat Ini\n- Status: {client['status']}\n- Job aktif: {client['active_job']}")
            return "\n\n".join(sections)

    def list_clients(self, platform: str = None) -> list:
        with self._get_conn() as conn:
            if platform:
                rows = conn.execute('SELECT platform, username FROM clients WHERE platform = ?', (platform,)).fetchall()
            else:
                rows = conn.execute('SELECT platform, username FROM clients').fetchall()
            return [{"platform": r["platform"], "username": r["username"]} for r in rows]
