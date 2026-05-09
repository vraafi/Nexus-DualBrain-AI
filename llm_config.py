"""
llm_config.py — Konfigurasi model LLM untuk Nexus DualBrain AI
Update: Model Gemini terbaru (Mei 2026)
"""

LLM_MODELS = {
    # ── Gemini 2.5 Pro: model terkuat, gunakan untuk code generation & negosiasi ──
    "gemini-2.5-pro": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
        "max_retries": 5,
        "timeout": 120,
        "rate_limit_delay": 60,
        "supports_thinking": True,
    },
    # ── Gemini 2.5 Flash: cepat & hemat, untuk screening job & negosiasi ringan ──
    "gemini-2.5-flash": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        "max_retries": 5,
        "timeout": 60,
        "rate_limit_delay": 30,
        "supports_thinking": True,
    },
    # ── Gemini 2.0 Flash: fallback tercepat, hemat kuota ──
    "gemini-2.0-flash": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "max_retries": 5,
        "timeout": 45,
        "rate_limit_delay": 20,
        "supports_thinking": False,
    },
}

# Model default: Gemini 2.5 Flash — cepat, hemat, tetap sangat capable
DEFAULT_LLM_MODEL = "gemini-2.5-flash"

# Model untuk code generation (butuh reasoning mendalam)
CODEGEN_MODEL = "gemini-2.5-pro"

# Model fallback jika quota habis
FALLBACK_MODEL = "gemini-2.0-flash"
