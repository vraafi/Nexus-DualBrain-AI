"""
difficulty_classifier.py — Nexus DualBrain AI
===============================================
Sistem klasifikasi kesulitan pekerjaan freelance SEBELUM agent melamar.

Metodologi berdasarkan 3 repo GitHub terbukti yang dipakai ribuan developer:

1. radon (https://github.com/rubik/radon) — 1.5k+ stars
   Cyclomatic Complexity grades A-F:
   A (1-5): Simple, low risk
   B (6-10): Medium, stable
   C (11-15): Moderate, unstable
   D-F (16+): Complex, error-prone, high risk
   → Kita terjemahkan ke level MUDAH/SEDANG/SULIT dari DESKRIPSI job

2. cognitive-complexity (SonarSource methodology)
   https://www.sonarsource.com/docs/CognitiveComplexity.pdf
   Dipakai GitHub, GitLab, SonarQube (jutaan repo)
   Prinsip: BUKAN jumlah branch, tapi seberapa SULIT kode dipahami manusia.
   → Kita estimasi cognitive load dari kata-kata dalam job description

3. wily (https://github.com/tonybaloney/wily) — 1.2k+ stars
   Metrics: LOC (Lines of Code), Complexity, Maintainability Index
   Formula MI = 171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)
   → Kita estimasi LOC dari scope job description (endpoints, tables, pages, dll.)

=============================================================================
DEFINISI LEVEL KESULITAN — SANGAT DETAIL
=============================================================================

MUDAH (Skor 1-3) — AI BOLEH LAMAR — Probabilitas sukses 90-100%
-----------------------------------------------------------------
Karakteristik:
  - Satu fungsi utama, tidak ada integrasi silang
  - Estimasi kode < 200 baris Python
  - Tidak butuh arsitektur — langsung koding
  - Tidak ada state management yang kompleks
  - Output: satu file .py atau script sederhana
  - Waktu pengerjaan: 1-3 hari
  - Budget: $20-$150 atau < $25/jam

Contoh task MUDAH yang AI bisa kerjakan 100%:
  ✅ Script download gambar dari URL list
  ✅ Konversi file CSV ke JSON atau sebaliknya
  ✅ Web scraper 1 halaman statis (tidak ada JS rendering)
  ✅ Script kirim email otomatis dengan template
  ✅ Script rename/organize file berdasarkan aturan
  ✅ Bot Telegram/Discord dengan 2-3 command sederhana
  ✅ Script cek harga satu produk dari satu website
  ✅ Parser PDF/Word ke teks
  ✅ Script backup database ke file
  ✅ Cron job sederhana (kirim notifikasi, cek status)
  ✅ Pengambilan data dari satu REST API (read-only)
  ✅ Script filter/sort data Excel
  ✅ Simple password generator atau utility tool

SEDANG (Skor 4-6) — AI BOLEH LAMAR — Probabilitas sukses 70-89%
-----------------------------------------------------------------
Karakteristik:
  - 2-4 komponen yang saling terhubung
  - Estimasi kode 200-800 baris Python
  - Butuh desain sederhana sebelum koding
  - State management dasar (database SQLite/Postgres)
  - Output: package Python atau small web app
  - Waktu pengerjaan: 3-14 hari
  - Budget: $150-$600 atau $25-$60/jam

Contoh task SEDANG yang AI bisa kerjakan 100%:
  ✅ Web scraper multi-halaman dengan Selenium/Playwright (ada JS)
  ✅ REST API wrapper/client untuk layanan eksternal
  ✅ Bot Telegram/Discord dengan database (simpan user, history)
  ✅ ETL pipeline: ambil data dari 2-3 sumber, transform, simpan
  ✅ Web app CRUD sederhana dengan Flask/FastAPI (< 10 endpoint)
  ✅ Price monitor multi-produk multi-website + notifikasi
  ✅ Script automation login + form submission di website
  ✅ Data pipeline: API → transform → database → laporan CSV
  ✅ Dashboard sederhana dengan Chart.js atau matplotlib
  ✅ Automation workflow multi-step (trigger → action → notifikasi)
  ✅ Email parser otomatis (baca inbox, ekstrak data, simpan DB)
  ✅ File watcher + processor (PDF OCR, upload ke Google Drive)
  ✅ Simple CLI tool dengan argparse dan beberapa subcommand
  ✅ Integrasi 2 API (misal: Notion + Telegram, Airtable + Slack)
  ✅ Scraper dengan login + navigasi multi-halaman + export Excel

SULIT (Skor 7-10) — AI DILARANG MELAMAR — Risiko gagal > 30%
--------------------------------------------------------------
Karakteristik:
  - 5+ komponen dengan integrasi kompleks
  - Estimasi kode > 800 baris atau arsitektur multi-file
  - Butuh design meeting/iterasi dengan klien
  - State management kompleks (transaksi, concurrency, locking)
  - Output: production system, platform, atau SaaS
  - Waktu pengerjaan: > 14 hari atau "ongoing"
  - Budget: > $600 atau > $60/jam atau tidak disebutkan tapi scope besar
  - Membutuhkan pengalaman senior engineer

Contoh task SULIT yang AI TIDAK BOLEH AMBIL:
  ❌ Training ML/Deep Learning model dari scratch (custom dataset)
  ❌ Sistem real-time (< 100ms latency, WebSocket + concurrent users)
  ❌ Full-stack web app kompleks (React + Node/Django + Redis + Auth)
  ❌ Mobile app (iOS/Android/React Native)
  ❌ Microservices/distributed system (Docker + K8s + service mesh)
  ❌ Sistem dengan > 20 tabel database + relasi kompleks
  ❌ Security audit / penetration testing / VAPT
  ❌ Blockchain/smart contract development
  ❌ Video/audio processing pipeline (encoding, streaming, CDN)
  ❌ Computer vision dari scratch (custom model, bukan API)
  ❌ DevOps/Infrastructure as Code (Terraform, Ansible, CI/CD setup)
  ❌ E-commerce platform dengan payment gateway + inventory
  ❌ Multi-tenant SaaS dengan billing, auth, dashboard per tenant
  ❌ ERP/CRM integration yang kompleks (SAP, Salesforce custom)
  ❌ Web scraper dengan anti-bot enterprise (Akamai, Cloudflare Pro)
  ❌ Job yang meminta "senior developer", "tech lead", "architect"
  ❌ Job dengan deadline sangat ketat < 24 jam untuk scope besar
  ❌ Job yang membutuhkan video call wajib untuk diskusi
  ❌ Job dengan NDA ketat + audit trail requirement
  ❌ Sistem dengan regulatory compliance (HIPAA, PCI-DSS, SOC2)
"""

import re
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SIGNAL DICTIONARIES — berbasis metodologi radon + SonarSource
# ═══════════════════════════════════════════════════════════════

# Sinyal KERAS yang langsung membuat job jadi SULIT (nilai +3 masing-masing)
HARD_BLOCKERS = [
    # Teknologi enterprise / distribusi
    "kubernetes", "k8s", "terraform", "ansible", "puppet", "chef",
    "microservices", "micro-services", "service mesh", "istio",
    "event sourcing", "cqrs", "saga pattern",
    # ML/AI dari scratch
    "train a model", "training dataset", "custom model", "fine-tuning",
    "neural network from scratch", "deep learning architecture",
    "computer vision model", "nlp model", "build an llm",
    # Mobile
    "ios app", "android app", "react native", "flutter", "swift", "kotlin",
    "app store", "google play", "mobile application",
    # Platform kompleks
    "saas platform", "multi-tenant", "white-label", "erp integration",
    "salesforce integration", "sap integration",
    "e-commerce platform", "marketplace platform",
    # Security & compliance
    "penetration testing", "pentest", "vapt", "security audit",
    "hipaa", "pci-dss", "pci dss", "soc2", "gdpr compliance system",
    "iso 27001",
    # Blockchain
    "smart contract", "solidity", "web3", "blockchain development",
    "nft marketplace", "defi", "crypto exchange",
    # Video/audio processing
    "video encoding", "ffmpeg pipeline", "streaming server",
    "live streaming", "webrtc", "hls", "dash streaming",
    # Real-time kompleks
    "real-time multiplayer", "game server", "websocket at scale",
    "1 million users", "high availability", "99.99% uptime",
    # Mandatory meetings
    "daily standup", "weekly meeting required", "must join call",
    "video interview required", "zoom meeting every",
]

# Sinyal SEDANG — menambah kompleksitas tapi tidak otomatis SULIT (nilai +1)
MEDIUM_SIGNALS = [
    # Framework web
    "django", "fastapi", "flask", "rest api", "restful api",
    "graphql", "grpc", "swagger", "openapi",
    # Database
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "database schema", "data model", "migrations", "orm",
    # Auth & security dasar
    "jwt", "oauth", "authentication", "authorization",
    "login system", "user management", "role-based access",
    # Frontend sederhana
    "react", "vue", "angular", "html css", "dashboard ui",
    "chart", "visualization", "plotly", "d3.js",
    # Browser automation
    "selenium", "playwright", "puppeteer", "chromium",
    "headless browser", "browser automation",
    # Integrasi API ganda
    "multiple api", "integrate with", "third-party api",
    "webhook", "api integration",
    # Docker dasar
    "docker", "containerize", "dockerfile", "docker-compose",
    # Queue/async
    "celery", "rabbitmq", "kafka", "task queue", "async processing",
    # Multi-halaman scraping
    "pagination", "infinite scroll", "dynamic content", "javascript rendering",
    # Deployment
    "deploy to", "heroku", "aws", "gcp", "azure", "vps", "cloud",
    "nginx", "gunicorn", "ssl certificate",
]

# Sinyal MUDAH — mengurangi skor kompleksitas (nilai -1)
EASY_SIGNALS = [
    "simple script", "small script", "basic script", "quick script",
    "python script", "automation script", "one-time script",
    "csv", "excel", "spreadsheet", "json to", "xml to", "convert",
    "download", "fetch", "read from", "parse",
    "single page", "one website", "one url", "one source",
    "telegram bot", "discord bot", "simple bot",
    "rename files", "organize files", "batch rename",
    "send email", "email template", "notify via",
    "cron job", "scheduler", "scheduled task",
    "price check", "stock check", "availability check",
    "no database needed", "flat file", "no backend",
    "beginner friendly", "straightforward", "no experience required",
    "small project", "mini project", "simple task",
    "read the documentation", "follow the api docs",
]

# Sinyal SCOPE BESAR — proxy untuk LOC estimation (nilai +1 per match)
SCOPE_SIGNALS = [
    r"\d+\s*endpoint", r"\d+\s*api", r"\d+\s*module",
    r"\d+\s*page", r"\d+\s*feature", r"\d+\s*function",
    r"\d+\s*table", r">\s*\d{3}\s*user", r"\d+\s*integration",
    r"full[\s-]stack", r"end[\s-]to[\s-]end", r"complete platform",
    r"entire system", r"from scratch", r"production[\s-]ready",
    r"scalab", r"enterprise[\s-]grade", r"large[\s-]scale",
]

# Sinyal BUDGET tinggi — proxy untuk kompleksitas
HIGH_BUDGET_PATTERNS = [
    r"\$[5-9]\d{2,}", r"\$[1-9]\d{3,}",   # $500+ atau $1000+
    r"[5-9]\d{2,}\s*(usd|dollar)",         # 500+ USD
    r"[1-9]\d{3,}\s*(usd|dollar)",         # 1000+ USD
    r"\$[6-9]\d\s*[/\\]?\s*hr",            # $60+/hr
    r"\$[1-9]\d{2}\s*[/\\]?\s*hr",         # $100+/hr
    r"long[\s-]term", r"ongoing", r"retainer",  # Long-term = high complexity
]

# Sinyal EXPERTISE TINGGI (nilai +2 masing-masing)
EXPERTISE_SIGNALS = [
    "senior developer", "senior engineer", "lead developer", "tech lead",
    "principal engineer", "staff engineer", "architect",
    "expert in", "expert with", "5+ years", "7+ years", "10+ years",
    "strong background", "deep knowledge", "extensive experience",
    "proven track record", "advanced knowledge", "mastery of",
]


class DifficultyClassifier:
    """
    Klasifikasi kesulitan pekerjaan dari teks deskripsi job.

    Metodologi:
    - Cyclomatic Complexity (radon): A=MUDAH, B=SEDANG, C-F=SULIT
    - Cognitive Complexity (SonarSource): estimasi dari kata kunci
    - Maintainability Index (wily): estimasi LOC dari scope signals

    Level Output:
    - MUDAH  (1-3): LAMAR — AI bisa 100%
    - SEDANG (4-6): LAMAR — AI bisa dengan effort
    - SULIT  (7+):  SKIP  — risiko gagal terlalu tinggi
    """

    LEVEL_MUDAH  = "MUDAH"
    LEVEL_SEDANG = "SEDANG"
    LEVEL_SULIT  = "SULIT"

    MAX_ALLOWED_SCORE = 7   # Skor 8+ = SULIT = DITOLAK

    def classify(self, job: dict) -> dict:
        """
        Klasifikasi satu job. Return dict dengan:
          level   : "MUDAH" | "SEDANG" | "SULIT"
          score   : int 1-10
          allowed : bool (True jika MUDAH atau SEDANG)
          reasons : list[str] penyebab skor tinggi/rendah
          detail  : str ringkasan untuk logging
        """
        title = job.get("title", "")
        desc  = job.get("description", "")
        text  = (title + " " + desc).lower()
        reasons = []
        score = 2  # Base score — default MUDAH

        # ── 1. HARD BLOCKER CHECK (langsung +6 per signal, satu saja = SULIT) ─
        # Satu hard blocker (skor ≥8) LANGSUNG menjadi SULIT.
        # Contoh: "kubernetes" → base 2 + 6 = 8 → SULIT
        hard_hits = [b for b in HARD_BLOCKERS if b in text]
        if hard_hits:
            score += len(hard_hits) * 6
            reasons.append(f"Hard blocker: {', '.join(hard_hits[:4])}")

        # ── 2. EXPERTISE REQUIREMENT (+3 per signal) ─────────────────────────
        # "Senior developer" = sulit bagi AI yang bekerja otonom
        expert_hits = [e for e in EXPERTISE_SIGNALS if e in text]
        if expert_hits:
            score += len(expert_hits) * 3
            reasons.append(f"Expertise tinggi: {', '.join(expert_hits[:3])}")

        # ── 3. MEDIUM SIGNALS (+1 per signal, max +4) ────────────────────────
        # selenium + playwright + postgresql + pagination = 4 medium = +4 = SEDANG
        # TIDAK MENJADI SULIT hanya karena banyak teknologi sedang dipakai
        medium_hits = [m for m in MEDIUM_SIGNALS if m in text]
        medium_add = min(len(medium_hits), 4)
        if medium_hits:
            score += medium_add
            reasons.append(f"Medium signals ({len(medium_hits)}): {', '.join(medium_hits[:4])}")

        # ── 4. SCOPE ESTIMATION (LOC proxy, +1 per signal, max +4) ──────────
        scope_hits = [s for s in SCOPE_SIGNALS if re.search(s, text)]
        scope_add = min(len(scope_hits), 4)
        if scope_hits:
            score += scope_add
            reasons.append(f"Scope besar ({len(scope_hits)} indikator)")

        # ── 5. BUDGET TINGGI (+1) ─────────────────────────────────────────────
        budget_hits = [b for b in HIGH_BUDGET_PATTERNS if re.search(b, text)]
        if budget_hits:
            score += 1
            reasons.append("Budget tinggi (mungkin scope besar)")

        # ── 6. EASY SIGNALS (kurangi skor, -1 per signal, max -3) ────────────
        easy_hits = [e for e in EASY_SIGNALS if e in text]
        easy_sub = min(len(easy_hits), 3)
        if easy_hits:
            score -= easy_sub
            reasons.append(f"Easy signals: {', '.join(easy_hits[:3])}")

        # Clamp skor ke rentang 1-10
        score = max(1, min(10, score))

        # ── 7. TENTUKAN LEVEL ─────────────────────────────────────────────────
        if score <= 3:
            level = self.LEVEL_MUDAH
        elif score <= 7:
            level = self.LEVEL_SEDANG
        else:
            level = self.LEVEL_SULIT

        allowed = score <= self.MAX_ALLOWED_SCORE

        detail = (
            f"[{level}] Skor {score}/10 | "
            f"{'✅ LAMAR' if allowed else '🚫 SKIP'} | "
            f"Job: {title[:50]}"
        )

        if not allowed:
            logger.warning(
                "[DifficultyClassifier] 🚫 SULIT — SKIP: '%s' | Skor: %d | Alasan: %s",
                title[:60], score, " | ".join(reasons[:3])
            )
        else:
            logger.info(
                "[DifficultyClassifier] %s '%s' | Skor: %d",
                "✅ MUDAH" if level == self.LEVEL_MUDAH else "⚠️  SEDANG",
                title[:60], score
            )

        return {
            "level":   level,
            "score":   score,
            "allowed": allowed,
            "reasons": reasons,
            "detail":  detail,
        }

    def filter_allowed(self, jobs: list) -> list:
        """
        Filter list job — hanya kembalikan MUDAH dan SEDANG.
        Job SULIT langsung dibuang dengan log jelas.

        Return: (allowed_jobs, stats_dict)
        """
        allowed = []
        stats = {"MUDAH": 0, "SEDANG": 0, "SULIT": 0}

        for job in jobs:
            result = self.classify(job)
            job["_difficulty"] = result
            level = result["level"]
            stats[level] += 1

            if result["allowed"]:
                allowed.append(job)
            else:
                logger.warning(
                    "[DifficultyClassifier] 🚫 DIBUANG (SULIT) | %s | Skor: %d | %s",
                    job.get("title", "")[:60],
                    result["score"],
                    " | ".join(result["reasons"][:2])
                )

        logger.info(
            "[DifficultyClassifier] Hasil filter: MUDAH=%d SEDANG=%d SULIT=%d (dibuang) | "
            "Total lolos: %d/%d",
            stats["MUDAH"], stats["SEDANG"], stats["SULIT"],
            len(allowed), len(jobs)
        )
        return allowed, stats
