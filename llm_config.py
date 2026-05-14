"""
llm_config.py — Konfigurasi model LLM untuk Nexus DualBrain AI
Update: Model roles diperbaiki (Mei 2026)

Hierarki Model (urutan prioritas):
  1. Primary  — gemma-4-31b-it         (1500 RPD, terkuat, default utama)
  2. Secondary — gemma-4-26b-a4b-it    (fallback pertama jika 31b gagal)
  3. Last Resort — gemini-3.1-flash-lite-preview  (20 RPD, hanya darurat)
"""

LLM_MODELS = {
    # ── Primary: Dense 31B — default untuk semua task (1500 RPD) ──
    "gemma-4-31b-it": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
        "max_retries": 5,
        "timeout": 180,
        "rate_limit_delay": 30,
        "supports_thinking": False,  # Dimatikan sementara untuk mencegah Error 500
    },

    # ── Secondary: MoE 26B — fallback pertama jika 31b habis/gagal ──
    "gemma-4-26b-a4b-it": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent",
        "max_retries": 5,
        "timeout": 120,
        "rate_limit_delay": 30,
        "supports_thinking": False,  # Dimatikan sementara
    },

    # ── Last Resort: Flash-Lite — hanya dipakai jika 31b DAN 26b sama-sama gagal ──
    # PERINGATAN: hanya 20 RPD! Jangan jadikan default.
    "gemini-3.1-flash-lite-preview": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent",
        "max_retries": 2,
        "timeout": 45,
        "rate_limit_delay": 60,
        "supports_thinking": False,
    },
}

# ── Role Assignment ──────────────────────────────────────────────────────────

# Default: gemma-4-31b-it (1500 RPD) — dipakai untuk semua task biasa
DEFAULT_LLM_MODEL = "gemma-4-31b-it"

# Codegen: model terkuat untuk generate kode Python production-ready
CODEGEN_MODEL = "gemma-4-31b-it"

# Negotiation: model menengah untuk reply klien, filter job, reasoning moderat
NEGOTIATION_MODEL = "gemma-4-26b-a4b-it"

# Fallback chain: 31b gagal → 26b → flash-lite (last resort, hemat quota)
FALLBACK_MODEL = "gemini-3.1-flash-lite-preview"
