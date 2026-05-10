"""
llm_config.py — Konfigurasi model LLM untuk Nexus DualBrain AI
Update: Model roles sesuai permintaan user (Mei 2026)

Hierarki Model:
  - Primary (Codegen & Negosiasi kompleks): gemma-4-31b-it
  - Secondary (Screening & Task ringan):     gemma-4-26b-a4b-it
  - Default / Fallback (High-frequency):     gemini-3.1-flash-lite-preview
"""

LLM_MODELS = {
    # ── Primary: Dense 31B untuk tugas paling berat (codegen, negosiasi kompleks) ──
    "gemma-4-31b-it": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
        "max_retries": 5,
        "timeout": 180,
        "rate_limit_delay": 30,
        "supports_thinking": True,
    },

    # ── Secondary: MoE 26B untuk reasoning menengah, filter job, reply negosiasi ──
    "gemma-4-26b-a4b-it": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent",
        "max_retries": 5,
        "timeout": 120,
        "rate_limit_delay": 30,
        "supports_thinking": True,
    },

    # ── Default / Fallback: Flash-Lite untuk high-frequency tasks (hemat quota) ──
    "gemini-3.1-flash-lite-preview": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent",
        "max_retries": 5,
        "timeout": 45,
        "rate_limit_delay": 15,
        "supports_thinking": False,
    },
}

# ── Role Assignment ──────────────────────────────────────────────────────────

# Default: model paling hemat untuk task high-frequency (screening, heartbeat, dll)
DEFAULT_LLM_MODEL = "gemini-3.1-flash-lite-preview"

# Codegen: model terkuat untuk generate kode Python production-ready
CODEGEN_MODEL = "gemma-4-31b-it"

# Negotiation: model menengah untuk reply klien, filter job, reasoning moderat
NEGOTIATION_MODEL = "gemma-4-26b-a4b-it"

# Fallback: jika semua key primary gagal, turun ke model paling ringan
FALLBACK_MODEL = "gemini-3.1-flash-lite-preview"
