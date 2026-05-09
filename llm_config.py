LLM_MODELS = {
    "gemini-pro": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
        "max_retries": 5,
        "timeout": 90,
        "rate_limit_delay": 60 # seconds
    },
    "gemma-7b-it": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/gemma-7b-it:generateContent",
        "max_retries": 5,
        "timeout": 90,
        "rate_limit_delay": 60
    },
    "gpt-4o": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "max_retries": 5,
        "timeout": 120,
        "rate_limit_delay": 30,
        "api_type": "openai"
    }
}


DEFAULT_LLM_MODEL = "gemma-7b-it"
