"""NoVa LeadScore — Pre-run Validation (5 layers).

Check Python, packages, .env keys, folders, network.
Fail fast: report ALL errors at once.
"""

import importlib
import os
import sys
from loguru import logger


REQUIRED_PACKAGES = [
    ("streamlit", "streamlit"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("litellm", "litellm"),
    ("loguru", "loguru"),
    ("plotly", "plotly"),
]

REQUIRED_ENV_VARS = {
    "LLM_API_KEY": {
        "alt": ["GOOGLE_AI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"],
        "hint": "Get from: https://aistudio.google.com/apikey (Gemini) or provider dashboard",
    },
}

OPTIONAL_ENV_VARS = {
    "LLM_MODEL": "Default: gemini/gemini-2.5-flash. Options: claude-sonnet-4-6, groq/llama3-70b",
    "FALLBACK_LLM_MODEL": "Secondary model when primary fails",
}


def validate_full_setup() -> tuple[bool, list[str], list[str]]:
    """Check 5 layers. Returns (ok, errors, warnings).

    Layer 1: Python version
    Layer 2: Required packages
    Layer 3: .env keys
    Layer 4: Folder permissions
    Layer 5: Network (optional, non-blocking)
    """
    errors = []
    warnings = []

    # Layer 1: Python version
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        errors.append(f"Python 3.10+ required, got {v.major}.{v.minor}. Install: brew install python@3.13")
    else:
        logger.debug(f"Python {v.major}.{v.minor}.{v.micro} OK")

    # Layer 2: Required packages
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            errors.append(f"Missing package: {pip_name}. Fix: pip install {pip_name}")

    # Layer 3: .env keys
    for var, info in REQUIRED_ENV_VARS.items():
        value = os.getenv(var, "")
        if not value:
            # Check alternate var names
            alt_found = False
            for alt in info.get("alt", []):
                if os.getenv(alt, ""):
                    alt_found = True
                    break
            if not alt_found:
                errors.append(f"Missing {var} (or {', '.join(info.get('alt', []))}). {info['hint']}")

    for var, hint in OPTIONAL_ENV_VARS.items():
        if not os.getenv(var, ""):
            warnings.append(f"Optional: {var} not set. {hint}")

    # Layer 4: Folder permissions (write check)
    try:
        test_path = "/tmp/_leadscore_validate_test"
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
    except OSError as e:
        errors.append(f"Cannot write to temp directory: {e}")

    # Layer 5: Network (non-blocking warning)
    try:
        import urllib.request
        urllib.request.urlopen("https://generativelanguage.googleapis.com", timeout=5)
    except Exception:
        warnings.append("Cannot reach Google AI API. Check internet connection for AI scoring.")

    ok = len(errors) == 0

    if ok:
        logger.info(f"Validation passed ({len(warnings)} warnings)")
    else:
        logger.error(f"Validation failed: {len(errors)} errors, {len(warnings)} warnings")

    return ok, errors, warnings


def validate_dataframe(df, max_leads: int = 500, max_cols: int = 20) -> tuple[bool, list[str]]:
    """Validate uploaded DataFrame before processing."""
    errors = []

    if df is None or df.empty:
        errors.append("File is empty or could not be read.")
        return False, errors

    if len(df) > max_leads:
        errors.append(f"Too many leads: {len(df)} (max {max_leads}). Try splitting your file.")

    if len(df.columns) > max_cols:
        errors.append(f"Too many columns: {len(df.columns)} (max {max_cols}). Remove unnecessary columns.")

    if len(df.columns) < 2:
        errors.append("Need at least 2 columns to score leads (e.g., name + email).")

    return len(errors) == 0, errors
