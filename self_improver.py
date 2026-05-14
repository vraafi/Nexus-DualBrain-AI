"""
self_improver.py — AGI Self-Reflection & Continuous Improvement Loop
====================================================================
Komponen paling penting untuk AGI-lite: kemampuan agent untuk
mengevaluasi dirinya sendiri dan memperbaiki strategi.

Setiap 24 jam (atau setiap N cycle):
1. Analisis semua proposal yang dikirim → berapa % yang dibalas
2. Analisis semua job yang diapply → berapa % yang menang
3. LLM reflection: "Apa yang salah? Apa yang bisa diimprove?"
4. Update SOUL.md dengan strategi baru
5. Kirim laporan ke Telegram

Ini adalah komponen yang membuat Nexus makin pintar setiap hari.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

SOUL_PATH = os.path.join(os.path.dirname(__file__), "SOUL.md")
REFLECTION_DB = os.path.join(os.path.dirname(__file__), "output", "reflections.db")
REFLECTION_LOG = os.path.join(os.path.dirname(__file__), "output", "reflection_history.md")


class SelfImprover:
    """
    Self-reflection engine untuk Nexus DualBrain AI.

    AGI loop:
    1. Kumpulkan data performa (proposal, jobs, deliveries)
    2. Analisis dengan LLM: apa yang works, apa yang tidak
    3. Generate insight dan action items
    4. Update SOUL.md dengan lessons learned
    5. Track improvement over time
    """

    def __init__(self, llm_client=None, skill_library=None, job_scorer=None):
        os.makedirs(os.path.dirname(REFLECTION_DB), exist_ok=True)
        self.llm = llm_client
        self.skill_lib = skill_library
        self.job_scorer = job_scorer
        self._init_db()
        logger.info("[SelfImprover] AGI self-reflection engine aktif.")

    def _init_db(self):
        with sqlite3.connect(REFLECTION_DB) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reflected_at DATETIME,
                    period TEXT,
                    metrics TEXT,
                    insights TEXT,
                    action_items TEXT,
                    soul_updated INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at DATETIME,
                    metric_name TEXT,
                    metric_value REAL,
                    context TEXT
                );
            """)

    # ─── MAIN REFLECTION ────────────────────────────────────────────────────────

    def reflect(self, force: bool = False) -> dict:
        """
        Jalankan self-reflection cycle.
        force=True: paksa refleksi meski belum 24 jam.

        Returns: dict berisi insights dan action items.
        """
        if not force and not self._should_reflect():
            logger.info("[SelfImprover] Belum waktunya refleksi (< 24 jam).")
            return {}

        logger.info("[SelfImprover] 🤔 Memulai self-reflection cycle...")

        # 1. Kumpulkan metrics
        metrics = self._collect_metrics()

        # 2. Generate insight dengan LLM
        insights = self._generate_insights(metrics)

        # 3. Update SOUL.md
        soul_updated = False
        if insights.get("action_items"):
            soul_updated = self._update_soul(insights)

        # 4. Simpan ke DB
        self._save_reflection(metrics, insights, soul_updated)

        # 5. Log ke file
        self._log_reflection(metrics, insights)

        logger.info(
            "[SelfImprover] ✅ Reflection selesai. %d insights, %d action items.",
            len(insights.get("insights", [])),
            len(insights.get("action_items", []))
        )

        return insights

    def get_reflection_summary(self) -> str:
        """Summary refleksi terbaru untuk Telegram /think."""
        try:
            with sqlite3.connect(REFLECTION_DB) as conn:
                row = conn.execute("""
                    SELECT reflected_at, metrics, insights, action_items
                    FROM reflections ORDER BY id DESC LIMIT 1
                """).fetchone()
            if not row:
                return "❌ Belum ada reflection data. Jalankan /think untuk trigger."

            reflected_at, metrics_json, insights_json, actions_json = row
            metrics = json.loads(metrics_json or "{}")
            insights_data = json.loads(insights_json or "{}")
            actions = json.loads(actions_json or "[]")

            lines = [
                f"🤔 *Last Self-Reflection*",
                f"Waktu: {reflected_at[:16]}",
                "",
                f"📊 *Metrics 24 Jam:*",
                f"• Proposal terkirim: {metrics.get('proposals_sent', 0)}",
                f"• Job dimenangkan: {metrics.get('jobs_won', 0)}",
                f"• Deliveries sukses: {metrics.get('deliveries_success', 0)}",
                f"• Win rate: {metrics.get('win_rate', 0):.0f}%",
                "",
            ]

            if insights_data.get("key_insight"):
                lines.append(f"💡 *Key Insight:*")
                lines.append(f"_{insights_data['key_insight']}_")
                lines.append("")

            if actions:
                lines.append(f"✅ *Action Items:*")
                for i, action in enumerate(actions[:3], 1):
                    lines.append(f"{i}. {action}")

            return "\n".join(lines)
        except Exception as e:
            logger.error("[SelfImprover] Gagal get summary: %s", e)
            return "❌ Gagal ambil reflection summary."

    def record_metric(self, name: str, value: float, context: str = ""):
        """Record sebuah metric untuk analisis."""
        try:
            with sqlite3.connect(REFLECTION_DB) as conn:
                conn.execute(
                    "INSERT INTO performance_metrics (recorded_at, metric_name, metric_value, context) VALUES (?, ?, ?, ?)",
                    (datetime.now().isoformat(), name, value, context)
                )
        except Exception as e:
            logger.debug("[SelfImprover] Gagal record metric: %s", e)

    # ─── PRIVATE: DATA COLLECTION ───────────────────────────────────────────────

    def _collect_metrics(self) -> dict:
        """Kumpulkan semua metrics relevan dari 24 jam terakhir."""
        metrics = {
            "period": "24h",
            "collected_at": datetime.now(WIB).isoformat(),
            "proposals_sent": 0,
            "jobs_won": 0,
            "deliveries_success": 0,
            "deliveries_failed": 0,
            "win_rate": 0.0,
            "delivery_rate": 0.0,
            "avg_job_score": 0.0,
            "total_revenue": 0.0,
            "skill_templates_count": 0,
            "error_patterns": [],
        }

        # Ambil dari job_scores DB
        try:
            score_db = os.path.join(os.path.dirname(__file__), "output", "job_scores.db")
            if os.path.exists(score_db):
                with sqlite3.connect(score_db) as conn:
                    metrics["proposals_sent"] = conn.execute(
                        "SELECT COUNT(*) FROM job_scores WHERE applied = 1 AND scored_at >= datetime('now', '-24 hours')"
                    ).fetchone()[0]
                    metrics["jobs_won"] = conn.execute(
                        "SELECT COUNT(*) FROM job_scores WHERE outcome = 'hired' AND scored_at >= datetime('now', '-24 hours')"
                    ).fetchone()[0]
                    avg = conn.execute(
                        "SELECT AVG(score) FROM job_scores WHERE scored_at >= datetime('now', '-24 hours')"
                    ).fetchone()[0]
                    metrics["avg_job_score"] = round(avg or 0, 1)

            if metrics["proposals_sent"] > 0:
                metrics["win_rate"] = round(
                    metrics["jobs_won"] / metrics["proposals_sent"] * 100, 1
                )
        except Exception as e:
            logger.debug("[SelfImprover] Gagal collect score metrics: %s", e)

        # Ambil dari skill library
        try:
            skill_db = os.path.join(os.path.dirname(__file__), "output", "skill_library.db")
            if os.path.exists(skill_db):
                with sqlite3.connect(skill_db) as conn:
                    metrics["skill_templates_count"] = conn.execute(
                        "SELECT COUNT(*) FROM skills"
                    ).fetchone()[0]
        except Exception as e:
            logger.debug("[SelfImprover] Gagal collect skill metrics: %s", e)

        # Ambil dari error learning DB
        try:
            err_db = os.path.join(os.path.dirname(__file__), "error_patterns.db")
            if os.path.exists(err_db):
                with sqlite3.connect(err_db) as conn:
                    errors = conn.execute("""
                        SELECT error_type, COUNT(*) as count
                        FROM error_logs
                        WHERE timestamp >= datetime('now', '-24 hours')
                        GROUP BY error_type ORDER BY count DESC LIMIT 5
                    """).fetchall()
                    metrics["error_patterns"] = [{"type": e[0], "count": e[1]} for e in errors]
        except Exception as e:
            logger.debug("[SelfImprover] Gagal collect error metrics: %s", e)

        # Ambil dari financial tracker
        try:
            fin_db = os.path.join(os.path.dirname(__file__), "output", "financial.db")
            if os.path.exists(fin_db):
                with sqlite3.connect(fin_db) as conn:
                    result = conn.execute(
                        "SELECT SUM(revenue) FROM earnings WHERE created_at >= datetime('now', '-24 hours')"
                    ).fetchone()[0]
                    metrics["total_revenue"] = float(result or 0)
        except Exception as e:
            logger.debug("[SelfImprover] Gagal collect financial metrics: %s", e)

        logger.info("[SelfImprover] Metrics terkumpul: %s", json.dumps(metrics, indent=2))
        return metrics

    # ─── PRIVATE: LLM REFLECTION ────────────────────────────────────────────────

    def _generate_insights(self, metrics: dict) -> dict:
        """Gunakan LLM untuk generate insights dari metrics."""
        default_insights = {
            "key_insight": "Baru memulai, belum cukup data untuk analisis mendalam.",
            "insights": ["Terus kumpulkan data proposal dan deliveries."],
            "action_items": [
                "Pastikan semua proposals dilacak dengan benar",
                "Fokus pada niche Python automation dan web scraping",
                "Apply ke minimal 5 job per sesi Upwork"
            ],
            "strategy_update": None
        }

        if not self.llm:
            return default_insights

        # Buat prompt refleksi (Mengadopsi System Prompt Hermes Agent)
        metrics_text = json.dumps(metrics, indent=2, ensure_ascii=False)
        prompt = f"""<system>
You are Hermes, an advanced autonomous AGI system with recursive self-improvement capabilities.
Your current objective is to run a deep self-reflection cycle on your recent performance data.
You operate on a 'DualBrain' architecture, orchestrating multiple sub-models for execution.
</system>

<performance_data>
{metrics_text}
</performance_data>

<instructions>
Analyze the performance data strictly and objectively. Use the following reasoning structure:
1. Identify any anomalies or failures (e.g., low win rate, high delivery failures, specific error types).
2. Trace the root cause of these failures. Were the proposals too generic? Did the browser agent timeout? 
3. Formulate a precise, actionable strategy update that changes your behavior moving forward.

Respond ONLY with a valid JSON object following this exact schema:
{{
  "key_insight": "A single, highly analytical sentence summarizing the core finding.",
  "insights": [
    "Specific insight 1 regarding win rate or job selection",
    "Specific insight 2 regarding execution or code quality",
    "Specific insight 3 regarding client interaction or errors"
  ],
  "action_items": [
    "Immediate technical or behavioral change 1",
    "Immediate technical or behavioral change 2",
    "Immediate technical or behavioral change 3"
  ],
  "strategy_update": "A highly specific, one-sentence rule to be added to SOUL.md. E.g., 'Never apply to jobs requiring GUI applications' or 'Always verify the file path before calling Jules CLI.' If no update is needed, use null."
}}
</instructions>"""
        try:
            response = self.llm.generate_content(
                prompt,
                require_json=True,
                use_negotiation_model=True
            )
            if response:
                # Clean JSON if wrapped in markdown
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].strip()

                parsed = json.loads(response)
                logger.info("[SelfImprover] LLM insights berhasil digenerate.")
                return parsed
        except Exception as e:
            logger.error("[SelfImprover] Gagal generate insights: %s", e)

        return default_insights

    # ─── PRIVATE: SOUL UPDATE ───────────────────────────────────────────────────

    def _update_soul(self, insights: dict) -> bool:
        """Update SOUL.md dengan lessons learned dari reflection."""
        try:
            with open(SOUL_PATH, "r", encoding="utf-8") as f:
                soul_content = f.read()

            strategy_update = insights.get("strategy_update")
            if not strategy_update:
                return False

            # Tambahkan section Lessons Learned jika belum ada
            timestamp = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
            lessons_section = f"\n## Lessons Learned (Auto-Updated)\n"
            new_lesson = f"- [{timestamp}] {strategy_update}\n"

            if "## Lessons Learned" in soul_content:
                soul_content = soul_content.replace(
                    "## Lessons Learned (Auto-Updated)\n",
                    f"## Lessons Learned (Auto-Updated)\n{new_lesson}"
                )
            else:
                soul_content += lessons_section + new_lesson

            with open(SOUL_PATH, "w", encoding="utf-8") as f:
                f.write(soul_content)

            logger.info("[SelfImprover] SOUL.md diupdate dengan lessons learned.")
            return True
        except Exception as e:
            logger.error("[SelfImprover] Gagal update SOUL.md: %s", e)
            return False

    # ─── PRIVATE: PERSISTENCE ───────────────────────────────────────────────────

    def _should_reflect(self) -> bool:
        """Cek apakah sudah waktunya refleksi (minimal 24 jam sejak terakhir)."""
        try:
            with sqlite3.connect(REFLECTION_DB) as conn:
                last = conn.execute(
                    "SELECT reflected_at FROM reflections ORDER BY id DESC LIMIT 1"
                ).fetchone()
            if not last:
                return True  # Belum pernah reflect
            last_time = datetime.fromisoformat(last[0])
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
            return elapsed >= 86400  # 24 jam
        except Exception:
            return True

    def _save_reflection(self, metrics: dict, insights: dict, soul_updated: bool):
        """Simpan hasil refleksi ke DB."""
        try:
            with sqlite3.connect(REFLECTION_DB) as conn:
                conn.execute("""
                    INSERT INTO reflections
                    (reflected_at, period, metrics, insights, action_items, soul_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now(WIB).isoformat(),
                    "24h",
                    json.dumps(metrics),
                    json.dumps(insights),
                    json.dumps(insights.get("action_items", [])),
                    1 if soul_updated else 0
                ))
        except Exception as e:
            logger.error("[SelfImprover] Gagal save reflection: %s", e)

    def _log_reflection(self, metrics: dict, insights: dict):
        """Log refleksi ke markdown file untuk review manual."""
        try:
            timestamp = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
            log_entry = f"""
## Reflection — {timestamp}

### Metrics
- Proposals: {metrics.get('proposals_sent', 0)} sent, {metrics.get('jobs_won', 0)} won
- Win Rate: {metrics.get('win_rate', 0):.1f}%
- Deliveries: {metrics.get('deliveries_success', 0)} success
- Revenue: ${metrics.get('total_revenue', 0):.2f}
- Skill templates: {metrics.get('skill_templates_count', 0)}

### Key Insight
{insights.get('key_insight', 'N/A')}

### Action Items
"""
            for i, action in enumerate(insights.get("action_items", []), 1):
                log_entry += f"{i}. {action}\n"

            if insights.get("strategy_update"):
                log_entry += f"\n### Strategy Update\n{insights['strategy_update']}\n"

            log_entry += "\n---\n"

            with open(REFLECTION_LOG, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            logger.debug("[SelfImprover] Gagal log reflection: %s", e)
