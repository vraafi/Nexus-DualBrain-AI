"""
skill_library.py — Dynamic Skill Library untuk Nexus DualBrain AI
==================================================================
Komponen AGI-lite: belajar dari setiap deliverable sukses.

- Setiap job yang berhasil didelivery → simpan sebagai "skill template"
- Saat job baru masuk → cari skill template paling mirip → seed codegen
- Makin banyak job selesai → kualitas kode makin tinggi
- Self-improving: agent makin pintar setiap delivery
"""

import os
import json
import sqlite3
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
SKILL_DB = os.path.join(os.path.dirname(__file__), "output", "skill_library.db")
SKILL_CODE_DIR = os.path.join(os.path.dirname(__file__), "output", "skill_templates")


class SkillLibrary:
    """
    Library skill yang tumbuh secara otomatis dari pengalaman delivery.

    Setiap job yang berhasil disimpan sebagai template:
    - Metadata: platform, title, tech_stack, approach, budget
    - Code snapshot: kode yang lulus sandbox
    - Embedding keywords: untuk similarity search

    Saat codegen diminta:
    1. Cari template paling mirip berdasarkan keyword similarity
    2. Gunakan sebagai "seed" prompt → kode lebih berkualitas
    3. Track berapa kali template dipakai → popular templates = reliable patterns
    """

    def __init__(self, db_path: str = SKILL_DB):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(SKILL_CODE_DIR, exist_ok=True)
        self.db_path = db_path
        self._init_db()
        logger.info("[SkillLibrary] Inisialisasi selesai. DB: %s", db_path)

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT UNIQUE,
                    created_at DATETIME,
                    platform TEXT,
                    title TEXT,
                    description TEXT,
                    tech_stack TEXT,
                    approach TEXT,
                    keywords TEXT,
                    code_path TEXT,
                    budget REAL,
                    times_used INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 1.0
                );

                CREATE TABLE IF NOT EXISTS skill_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT,
                    used_at DATETIME,
                    job_title TEXT,
                    outcome TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_skills_platform ON skills(platform);
                CREATE INDEX IF NOT EXISTS idx_skills_keywords ON skills(keywords);
            """)

    # ─── SAVE: Simpan deliverable sukses ───────────────────────────────────────

    def save_success(
        self,
        platform: str,
        job_title: str,
        job_description: str,
        code: str,
        budget: float = 0.0,
        tech_stack: str = "",
        approach: str = ""
    ) -> str:
        """
        Simpan deliverable sukses sebagai skill template.
        Dipanggil setelah sandbox PASS dan delivery sukses.

        Returns: skill_id yang dibuat
        """
        skill_id = hashlib.md5(
            f"{platform}:{job_title}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        # Auto-detect tech stack dari code jika tidak disediakan
        if not tech_stack:
            tech_stack = self._detect_tech_stack(code)

        # Auto-extract approach dari description
        if not approach:
            approach = self._extract_approach(job_description)

        # Keywords untuk similarity search
        keywords = self._extract_keywords(job_title, job_description, tech_stack)

        # Simpan code ke file
        code_filename = f"{skill_id}_{platform}_{datetime.now().strftime('%Y%m%d')}.py"
        code_path = os.path.join(SKILL_CODE_DIR, code_filename)
        try:
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(f"# Skill Template: {job_title}\n")
                f.write(f"# Platform: {platform} | Budget: ${budget}\n")
                f.write(f"# Tech Stack: {tech_stack}\n")
                f.write(f"# Saved: {datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')}\n\n")
                f.write(code)
        except Exception as e:
            logger.error("[SkillLibrary] Gagal simpan code: %s", e)
            code_path = ""

        # Simpan metadata ke DB
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO skills
                    (skill_id, created_at, platform, title, description,
                     tech_stack, approach, keywords, code_path, budget)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    skill_id,
                    datetime.now(WIB).isoformat(),
                    platform, job_title,
                    job_description[:500],  # truncate
                    tech_stack, approach,
                    json.dumps(keywords),
                    code_path, budget
                ))
            logger.info(
                "[SkillLibrary] ✅ Skill baru disimpan: %s | %s | %s",
                skill_id, platform, job_title
            )
        except Exception as e:
            logger.error("[SkillLibrary] Gagal simpan skill ke DB: %s", e)

        return skill_id

    # ─── FIND: Cari template paling mirip ─────────────────────────────────────

    def find_similar(
        self,
        job_title: str,
        job_description: str,
        platform: str = None,
        top_k: int = 3
    ) -> list[dict]:
        """
        Cari skill template yang paling mirip dengan job baru.
        Returns list of matching skills dengan score similarity.
        """
        query_keywords = set(self._extract_keywords(job_title, job_description))
        if not query_keywords:
            return []

        try:
            with sqlite3.connect(self.db_path) as conn:
                if platform:
                    cursor = conn.execute(
                        "SELECT * FROM skills WHERE platform = ? ORDER BY times_used DESC",
                        (platform,)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM skills ORDER BY times_used DESC"
                    )
                rows = cursor.fetchall()
        except Exception as e:
            logger.error("[SkillLibrary] Gagal query: %s", e)
            return []

        if not rows:
            return []

        # Calculate Jaccard similarity
        col_names = [d[0] for d in cursor.description]
        scored = []
        for row in rows:
            skill = dict(zip(col_names, row))
            try:
                skill_kw = set(json.loads(skill.get("keywords", "[]")))
                if not skill_kw:
                    continue
                intersection = query_keywords & skill_kw
                union = query_keywords | skill_kw
                score = len(intersection) / len(union) if union else 0
                if score > 0.1:  # threshold minimum
                    skill["similarity_score"] = round(score, 3)
                    scored.append(skill)
            except Exception:
                continue

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:top_k]

    def get_seed_prompt(
        self,
        job_title: str,
        job_description: str,
        platform: str = None
    ) -> str:
        """
        Generate seed prompt untuk codegen berdasarkan skill library.
        Jika ada template mirip, sisipkan sebagai referensi.
        """
        similar = self.find_similar(job_title, job_description, platform)
        if not similar:
            return ""

        best = similar[0]
        seed = f"\n\n[SKILL LIBRARY REFERENCE — Similarity: {best['similarity_score']:.0%}]\n"
        seed += f"Platform: {best['platform']} | Title: {best['title']}\n"
        seed += f"Tech Stack: {best['tech_stack']}\n"
        seed += f"Approach: {best['approach']}\n"

        # Load code sample jika ada
        if best.get("code_path") and os.path.exists(best["code_path"]):
            try:
                with open(best["code_path"], "r", encoding="utf-8") as f:
                    code_sample = f.read()
                # Ambil 50 baris pertama sebagai referensi struktur
                lines = code_sample.split("\n")[:50]
                seed += f"\nCode Structure Reference (first 50 lines):\n```python\n"
                seed += "\n".join(lines)
                seed += "\n```\n"
                seed += "Adapt this structure for the new job. Improve and expand as needed.\n"
            except Exception:
                pass

        # Update usage count
        self._update_usage(best["skill_id"], job_title)

        logger.info(
            "[SkillLibrary] Seed dari template '%s' (similarity %.0f%%)",
            best["title"], best["similarity_score"] * 100
        )
        return seed

    # ─── STATS ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Ambil statistik skill library untuk Telegram /status."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
                platforms = conn.execute(
                    "SELECT platform, COUNT(*) FROM skills GROUP BY platform"
                ).fetchall()
                most_used = conn.execute(
                    "SELECT title, times_used FROM skills ORDER BY times_used DESC LIMIT 3"
                ).fetchall()
            return {
                "total_skills": total,
                "by_platform": dict(platforms),
                "most_used": [{"title": t, "used": u} for t, u in most_used]
            }
        except Exception as e:
            logger.error("[SkillLibrary] Gagal get stats: %s", e)
            return {"total_skills": 0, "by_platform": {}, "most_used": []}

    def get_summary_text(self) -> str:
        """Text summary untuk Telegram."""
        stats = self.get_stats()
        lines = [f"📚 *Skill Library* — {stats['total_skills']} templates"]
        for plat, count in stats.get("by_platform", {}).items():
            lines.append(f"  • {plat.capitalize()}: {count} skills")
        if stats.get("most_used"):
            lines.append("\n🔥 Paling sering dipakai:")
            for item in stats["most_used"]:
                lines.append(f"  • {item['title'][:40]}... ({item['used']}x)")
        return "\n".join(lines)

    # ─── PRIVATE HELPERS ───────────────────────────────────────────────────────

    def _detect_tech_stack(self, code: str) -> str:
        """Auto-detect tech stack dari kode Python."""
        tech_map = {
            "requests": "requests",
            "beautifulsoup": "bs4",
            "selenium": "selenium",
            "playwright": "playwright",
            "pandas": "pandas",
            "numpy": "numpy",
            "asyncio": "asyncio",
            "aiohttp": "aiohttp",
            "flask": "flask",
            "fastapi": "fastapi",
            "sqlalchemy": "sqlalchemy",
            "sqlite3": "sqlite3",
            "paramiko": "paramiko",
            "boto3": "aws-boto3",
            "google": "google-cloud",
            "telegram": "telegram-bot",
        }
        detected = []
        code_lower = code.lower()
        for lib, name in tech_map.items():
            if lib in code_lower:
                detected.append(name)
        return ", ".join(detected[:5]) if detected else "python-stdlib"

    def _extract_approach(self, description: str) -> str:
        """Extract approach singkat dari deskripsi job."""
        keywords_approach = {
            "scraping": "web scraping",
            "automation": "browser automation",
            "api": "API integration",
            "database": "database management",
            "data processing": "data pipeline",
            "csv": "data export/import",
            "pdf": "document processing",
            "email": "email automation",
            "telegram": "telegram bot",
            "discord": "discord bot",
        }
        desc_lower = description.lower()
        for kw, approach in keywords_approach.items():
            if kw in desc_lower:
                return approach
        return "python scripting"

    def _extract_keywords(
        self, title: str, description: str, tech_stack: str = ""
    ) -> list:
        """Extract keywords untuk similarity matching."""
        # Stop words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "are", "was", "were",
            "have", "has", "had", "will", "would", "could", "should", "need",
            "want", "make", "create", "build", "develop", "write", "using",
            "use", "i", "my", "we", "our", "you", "your", "it", "this", "that"
        }
        text = f"{title} {description} {tech_stack}".lower()
        # Remove special chars
        import re
        text = re.sub(r"[^\w\s]", " ", text)
        words = text.split()
        keywords = [w for w in words if len(w) > 3 and w not in stop_words]
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return unique[:30]  # max 30 keywords

    def _update_usage(self, skill_id: str, job_title: str):
        """Update usage counter untuk skill template."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE skills SET times_used = times_used + 1 WHERE skill_id = ?",
                    (skill_id,)
                )
                conn.execute(
                    "INSERT INTO skill_usage (skill_id, used_at, job_title) VALUES (?, ?, ?)",
                    (skill_id, datetime.now().isoformat(), job_title)
                )
        except Exception as e:
            logger.debug("[SkillLibrary] Gagal update usage: %s", e)
