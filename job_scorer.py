"""
job_scorer.py — Intelligent Job Scoring untuk Nexus DualBrain AI
================================================================
AGI-lite component: score setiap job 0-100 sebelum apply.

Faktor scoring:
- Budget/rate vs target rate (30%)
- Klien rating & spending history (20%)
- Job complexity vs kemampuan (20%)
- Niche alignment dengan portfolio (15%)
- Win probability berdasarkan histori (15%)

Hanya apply ke job dengan score >= 60 → hemat connects, naikan win rate.
"""

import re
import json
import logging
import sqlite3
import os
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

SCORE_DB = os.path.join(os.path.dirname(__file__), "output", "job_scores.db")

# Kata kunci yang menandai job bernilai tinggi
HIGH_VALUE_KEYWORDS = {
    "python", "automation", "scraping", "api", "data", "bot", "script",
    "django", "flask", "fastapi", "postgresql", "mysql", "mongodb",
    "aws", "docker", "kubernetes", "microservices", "async",
    "machine learning", "ai", "nlp", "analysis",
}

# Kata kunci RED FLAG — hindari
RED_FLAG_KEYWORDS = {
    "urgent", "asap", "immediately", "5 minutes", "1 hour",
    "unpaid", "free", "volunteer", "internship", "spec work",
    "test task", "simple", "easy task", "quick task",
    "i have no budget", "low budget", "cheap", "very small",
}

# Niche target kita (berdasarkan skill library)
TARGET_NICHES = [
    "web scraping", "automation", "data processing", "api integration",
    "telegram bot", "discord bot", "data pipeline", "cli tool",
    "file processing", "browser automation", "email automation",
]


class JobScorer:
    """
    Scoring engine untuk menilai kualitas job sebelum apply.

    Usage:
        scorer = JobScorer()
        score, details = scorer.score_job(job_data)
        if score >= 60:
            apply_job(job_data)
    """

    def __init__(self, db_path: str = SCORE_DB, target_hourly_rate: float = 35.0):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.target_rate = target_hourly_rate
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS job_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scored_at DATETIME,
                    platform TEXT,
                    job_title TEXT,
                    job_url TEXT,
                    score REAL,
                    score_details TEXT,
                    applied INTEGER DEFAULT 0,
                    outcome TEXT
                );
            """)

    # ─── MAIN SCORING ──────────────────────────────────────────────────────────

    def score_job(self, job_data: dict) -> tuple[float, dict]:
        """
        Score sebuah job. Returns (score 0-100, details dict).

        job_data keys:
            title, description, budget, rate, client_rating,
            client_total_spent, platform, url
        """
        details = {}
        total_score = 0.0

        # 1. Budget Score (30 points)
        budget_score = self._score_budget(job_data, details)
        total_score += budget_score

        # 2. Client Quality Score (20 points)
        client_score = self._score_client(job_data, details)
        total_score += client_score

        # 3. Niche Alignment Score (20 points)
        niche_score = self._score_niche(job_data, details)
        total_score += niche_score

        # 4. Complexity Score (15 points)
        complexity_score = self._score_complexity(job_data, details)
        total_score += complexity_score

        # 5. Red Flag Penalty
        penalty = self._check_red_flags(job_data, details)
        total_score = max(0, total_score - penalty)

        # 6. Win History Bonus (15 points)
        history_bonus = self._score_history(job_data, details)
        total_score = min(100, total_score + history_bonus)

        total_score = round(total_score, 1)
        details["total_score"] = total_score
        details["recommendation"] = self._get_recommendation(total_score)

        # Simpan ke DB
        self._save_score(job_data, total_score, details)

        logger.info(
            "[JobScorer] %s → Score: %.1f/100 (%s)",
            job_data.get("title", "Unknown")[:40],
            total_score,
            details["recommendation"]
        )
        return total_score, details

    def filter_jobs(self, jobs: list[dict], min_score: float = 60.0) -> list[dict]:
        """Filter dan sort jobs berdasarkan score."""
        scored_jobs = []
        for job in jobs:
            score, details = self.score_job(job)
            if score >= min_score:
                job["_score"] = score
                job["_score_details"] = details
                scored_jobs.append(job)

        # Sort by score descending
        scored_jobs.sort(key=lambda x: x["_score"], reverse=True)
        logger.info(
            "[JobScorer] %d/%d job lulus filter (min_score=%.0f)",
            len(scored_jobs), len(jobs), min_score
        )
        return scored_jobs

    def update_outcome(self, job_url: str, outcome: str):
        """Update outcome job setelah diketahui (hired/rejected)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE job_scores SET outcome = ?, applied = 1 WHERE job_url = ?",
                    (outcome, job_url)
                )
        except Exception as e:
            logger.error("[JobScorer] Gagal update outcome: %s", e)

    def get_win_rate_by_score_range(self) -> dict:
        """Analisis win rate berdasarkan score range — untuk self-improvement."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT
                        CASE
                            WHEN score >= 80 THEN '80-100'
                            WHEN score >= 60 THEN '60-79'
                            WHEN score >= 40 THEN '40-59'
                            ELSE '0-39'
                        END as range,
                        COUNT(*) as total,
                        SUM(CASE WHEN outcome = 'hired' THEN 1 ELSE 0 END) as hired
                    FROM job_scores
                    WHERE applied = 1 AND outcome IS NOT NULL
                    GROUP BY range
                """)
                return {row[0]: {"total": row[1], "hired": row[2]} for row in cursor.fetchall()}
        except Exception as e:
            logger.error("[JobScorer] Gagal get win rate: %s", e)
            return {}

    # ─── SCORE COMPONENTS ──────────────────────────────────────────────────────

    def _score_budget(self, job_data: dict, details: dict) -> float:
        """Score berdasarkan budget/rate (0-30 points)."""
        budget = self._parse_budget(job_data)

        if budget <= 0:
            details["budget_score"] = 0
            details["budget_note"] = "No budget info"
            return 0

        # Konversi ke estimated hourly jika fixed
        job_type = job_data.get("job_type", "fixed").lower()
        if "hourly" in job_type or "hour" in job_type:
            hourly = budget
        else:
            # Asumsi fixed price job: estimasi 5-20 jam
            desc_lower = (job_data.get("description", "") + job_data.get("title", "")).lower()
            estimated_hours = 20 if "complex" in desc_lower or "large" in desc_lower else 10
            hourly = budget / estimated_hours

        ratio = hourly / self.target_rate
        if ratio >= 2.0:
            score = 30
            note = f"Excellent (${hourly:.0f}/h, {ratio:.1f}x target)"
        elif ratio >= 1.5:
            score = 25
            note = f"Great (${hourly:.0f}/h)"
        elif ratio >= 1.0:
            score = 20
            note = f"Good (${hourly:.0f}/h)"
        elif ratio >= 0.7:
            score = 12
            note = f"Below target (${hourly:.0f}/h)"
        elif ratio >= 0.5:
            score = 6
            note = f"Low (${hourly:.0f}/h)"
        else:
            score = 0
            note = f"Too low (${hourly:.0f}/h)"

        details["budget_score"] = score
        details["budget_note"] = note
        return score

    def _score_client(self, job_data: dict, details: dict) -> float:
        """Score berdasarkan kualitas klien (0-20 points)."""
        score = 10  # Base score untuk klien baru

        client_rating = float(job_data.get("client_rating") or 0)
        total_spent = self._parse_budget({"budget": job_data.get("client_total_spent", 0)})
        reviews_count = int(job_data.get("client_reviews", 0))

        if client_rating >= 4.8:
            score += 8
        elif client_rating >= 4.5:
            score += 5
        elif client_rating >= 4.0:
            score += 2
        elif 0 < client_rating < 3.5:
            score -= 5  # Klien bermasalah

        if total_spent >= 10000:
            score += 5
        elif total_spent >= 1000:
            score += 3
        elif total_spent >= 100:
            score += 1

        score = max(0, min(20, score))
        details["client_score"] = score
        details["client_note"] = (
            f"Rating: {client_rating:.1f}/5 | "
            f"Spent: ${total_spent:.0f} | "
            f"Reviews: {reviews_count}"
        )
        return score

    def _score_niche(self, job_data: dict, details: dict) -> float:
        """Score berdasarkan niche alignment (0-20 points)."""
        text = f"{job_data.get('title', '')} {job_data.get('description', '')}".lower()

        high_value_matches = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in text)
        niche_matches = sum(1 for niche in TARGET_NICHES if niche in text)

        score = min(20, (high_value_matches * 2) + (niche_matches * 4))
        details["niche_score"] = score
        details["niche_note"] = (
            f"High-value KW: {high_value_matches} | "
            f"Target niches: {niche_matches}"
        )
        return float(score)

    def _score_complexity(self, job_data: dict, details: dict) -> float:
        """
        Score berdasarkan kompleksitas vs kemampuan (0-15 points).
        Too simple = rendah (waste of time), Too complex = risiko tinggi.
        """
        desc = (job_data.get("description", "") + job_data.get("title", "")).lower()
        word_count = len(desc.split())

        # Indikator kompleksitas sedang-tinggi (sweet spot kita)
        mid_complexity_signals = [
            "integrate", "scrape", "automate", "process", "parse",
            "schedule", "monitor", "notify", "export", "transform",
            "api", "webhook", "database", "report",
        ]
        high_complexity_signals = [
            "distributed", "microservice", "real-time", "ml model",
            "neural", "kubernetes", "terraform", "multi-tenant",
        ]

        mid_count = sum(1 for s in mid_complexity_signals if s in desc)
        high_count = sum(1 for s in high_complexity_signals if s in desc)

        if high_count >= 3:
            score = 8  # Too complex — high risk
            note = "High complexity, risk of overrun"
        elif mid_count >= 3:
            score = 15  # Sweet spot
            note = "Good complexity match"
        elif mid_count >= 1:
            score = 10  # OK
            note = "Moderate complexity"
        elif word_count < 50:
            score = 3  # Too vague
            note = "Job description too short/vague"
        else:
            score = 6
            note = "Low complexity"

        details["complexity_score"] = score
        details["complexity_note"] = note
        return float(score)

    def _check_red_flags(self, job_data: dict, details: dict) -> float:
        """Cek red flags dan berikan penalty (0-50 points deduction)."""
        text = f"{job_data.get('title', '')} {job_data.get('description', '')}".lower()
        flags_found = [kw for kw in RED_FLAG_KEYWORDS if kw in text]
        penalty = min(50, len(flags_found) * 15)

        details["red_flags"] = flags_found
        details["red_flag_penalty"] = penalty
        if flags_found:
            logger.info("[JobScorer] Red flags: %s", flags_found)
        return float(penalty)

    def _score_history(self, job_data: dict, details: dict) -> float:
        """Bonus berdasarkan win history untuk niche yang sama (0-15 points)."""
        title_lower = job_data.get("title", "").lower()
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Cari job dengan keyword title yang mirip dan berhasil
                similar_wins = conn.execute("""
                    SELECT COUNT(*) FROM job_scores
                    WHERE outcome = 'hired' AND job_title LIKE ?
                """, (f"%{title_lower[:20]}%",)).fetchone()[0]

            if similar_wins >= 3:
                bonus = 15
            elif similar_wins >= 1:
                bonus = 8
            else:
                bonus = 0

            details["history_bonus"] = bonus
            details["history_note"] = f"{similar_wins} similar wins in history"
            return float(bonus)
        except Exception:
            details["history_bonus"] = 0
            return 0.0

    # ─── HELPERS ───────────────────────────────────────────────────────────────

    def _parse_budget(self, job_data: dict) -> float:
        """Parse budget dari berbagai format."""
        for key in ("budget", "rate", "budget_min", "budget_max"):
            val = job_data.get(key, 0)
            if val:
                try:
                    # Remove currency symbols and commas
                    cleaned = re.sub(r"[^\d.]", "", str(val))
                    return float(cleaned) if cleaned else 0.0
                except (ValueError, TypeError):
                    continue
        return 0.0

    def _get_recommendation(self, score: float) -> str:
        if score >= 80:
            return "🔥 HIGHLY RECOMMENDED — Apply ASAP"
        elif score >= 60:
            return "✅ APPLY"
        elif score >= 40:
            return "⚠️ MARGINAL — Apply only if quota available"
        else:
            return "❌ SKIP"

    def _save_score(self, job_data: dict, score: float, details: dict):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO job_scores
                    (scored_at, platform, job_title, job_url, score, score_details)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    job_data.get("platform", "unknown"),
                    job_data.get("title", ""),
                    job_data.get("url", ""),
                    score,
                    json.dumps(details)
                ))
        except Exception as e:
            logger.debug("[JobScorer] Gagal save score: %s", e)
