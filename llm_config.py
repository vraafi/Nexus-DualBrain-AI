"""
llm_config.py — Konfigurasi model LLM untuk Nexus DualBrain AI
Update: Model Gemini & Gemma terbaru via Google AI Studio (Mei 2026)
"""

LLM_MODELS = {
    # ── Gemini 3.1 Flash-Lite: model tercepat & termurah untuk screening job ──
    "gemini-3.1-flash-lite": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent",
        "max_retries": 5,
        "timeout": 45,
        "rate_limit_delay": 15,
        "supports_thinking": False,
    },
    
    # ── Gemini 3.1 Flash: lebih hemat dari 2.5 Pro untuk codegen ──
    "gemini-3.1-flash": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash:generateContent",
        "max_retries": 5,
        "timeout": 90,
        "rate_limit_delay": 30,
        "supports_thinking": True,
    },

    # ── Gemma 4 26B A4B: MoE model, ideal untuk reasoning menengah ──
    "gemma-4-26b-a4b-it": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent",
        "max_retries": 5,
        "timeout": 120,
        "rate_limit_delay": 30,
        "supports_thinking": True,
    },
    
    # ── Gemma 4 31B: Dense model, kualitas tertinggi untuk negosiasi kompleks ──
    "gemma-4-31b-it": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
        "max_retries": 5,
        "timeout": 180,
        "rate_limit_delay": 30,
        "supports_thinking": True,
    },
}

# Model default: Gemini 3.1 Flash-Lite (hemat biaya untuk high-frequency tasks)
DEFAULT_LLM_MODEL = "gemini-3.1-flash-lite"

# Model untuk code generation
CODEGEN_MODEL = "gemini-3.1-flash"

# Fallback jika model utama gagal (tetap menggunakan cloud API sesuai permintaan user)
FALLBACK_MODEL = "gemini-3.1-flash-lite"
