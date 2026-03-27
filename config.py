"""NoVa LeadScore — Configuration (swap-ready via .env)"""

import os
from dataclasses import dataclass

# === DEFAULTS (swap here) ===
DEFAULTS = {
    "LLM_MODEL": "gemini/gemini-2.5-flash",
    "LLM_API_KEY_VAR": "GOOGLE_AI_API_KEY",  # which .env var holds the key
    "EXPORT_FORMAT": "csv",
    "MAX_LEADS": 500,
    "BATCH_SIZE": 10,       # leads per AI call
    "MAX_RETRIES": 3,
    "RETRY_BACKOFF": 1.0,   # seconds, exponential
    "LOG_SINK": "console",
    "SCORE_MIN": 0,
    "SCORE_MAX": 100,
}


@dataclass
class Config:
    """Immutable config loaded from .env + defaults."""
    llm_model: str = ""
    llm_api_key: str = ""
    export_format: str = "csv"
    max_leads: int = 500
    batch_size: int = 10
    max_retries: int = 3
    retry_backoff: float = 1.0
    log_sink: str = "console"
    app_name: str = "NoVa LeadScore"
    version: str = "1.0.0"

    # Fallback provider (swap)
    fallback_model: str = ""
    fallback_api_key: str = ""

    def __post_init__(self):
        if not self.llm_model:
            self.llm_model = os.getenv("LLM_MODEL", DEFAULTS["LLM_MODEL"])
        if not self.llm_api_key:
            key_var = os.getenv("LLM_API_KEY_VAR", DEFAULTS["LLM_API_KEY_VAR"])
            self.llm_api_key = os.getenv("LLM_API_KEY", os.getenv(key_var, ""))
        if not self.fallback_model:
            self.fallback_model = os.getenv("FALLBACK_LLM_MODEL", "")
        if not self.fallback_api_key:
            self.fallback_api_key = os.getenv("FALLBACK_LLM_API_KEY", "")
        self.export_format = os.getenv("EXPORT_FORMAT", DEFAULTS["EXPORT_FORMAT"])
        self.max_leads = int(os.getenv("MAX_LEADS", DEFAULTS["MAX_LEADS"]))
        self.batch_size = int(os.getenv("BATCH_SIZE", DEFAULTS["BATCH_SIZE"]))
        self.max_retries = int(os.getenv("MAX_RETRIES", DEFAULTS["MAX_RETRIES"]))
        self.retry_backoff = float(os.getenv("RETRY_BACKOFF", DEFAULTS["RETRY_BACKOFF"]))
        self.log_sink = os.getenv("LOG_SINK", DEFAULTS["LOG_SINK"])


def get_config() -> Config:
    """Factory: load config from environment."""
    return Config()
