"""NoVa LeadScore — Lead Field Detector & Mapper.

Analyzes CSV/Excel structure: detect field types, auto-map common lead fields,
measure data completeness. No AI calls — pure pandas analysis.
"""

import re
from dataclasses import dataclass, field
import pandas as pd
from loguru import logger

# === DATA MODELS ===

@dataclass
class LeadField:
    """Single column analysis."""
    name: str
    dtype: str             # text, numeric, email, url, phone, categorical, datetime
    completeness: float    # 0-1 ratio of non-null values
    unique_count: int = 0
    sample_values: list = field(default_factory=list)


@dataclass
class LeadProfile:
    """Full dataset analysis result."""
    filename: str
    total_leads: int
    fields: list[LeadField] = field(default_factory=list)
    field_mapping: dict = field(default_factory=dict)  # role → column name
    quality_score: float = 0.0  # overall data quality 0-100


# === FIELD TYPE DETECTION ===

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
URL_PATTERN = re.compile(r"^https?://|^www\.", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"^[\+]?[\d\s\-\(\)\.]{7,20}$")


def _detect_field_type(series: pd.Series) -> str:
    """Detect the semantic type of a column."""
    non_null = series.dropna().astype(str)
    if non_null.empty:
        return "text"

    sample = non_null.head(50)

    # Check email
    if sample.apply(lambda x: bool(EMAIL_PATTERN.match(x.strip()))).mean() > 0.5:
        return "email"

    # Check URL
    if sample.apply(lambda x: bool(URL_PATTERN.match(x.strip()))).mean() > 0.5:
        return "url"

    # Check phone
    if sample.apply(lambda x: bool(PHONE_PATTERN.match(x.strip()))).mean() > 0.5:
        return "phone"

    # Check numeric
    try:
        pd.to_numeric(non_null)
        return "numeric"
    except (ValueError, TypeError):
        pass

    # Check datetime
    try:
        pd.to_datetime(non_null.head(20), format="mixed")
        return "datetime"
    except (ValueError, TypeError):
        pass

    # Check categorical (few unique values relative to total)
    if non_null.nunique() < min(20, len(non_null) * 0.3):
        return "categorical"

    return "text"


# === FIELD MAPPING ===

FIELD_ROLE_PATTERNS = {
    "name": r"(?i)(name|full.?name|contact.?name|lead.?name|first.?name|last.?name|nombre)",
    "email": r"(?i)(e.?mail|email.?address|correo)",
    "company": r"(?i)(company|organization|org|business|empresa|firm)",
    "title": r"(?i)(title|job.?title|position|role|designation|cargo)",
    "phone": r"(?i)(phone|tel|mobile|cell|telephone|whatsapp|telefono)",
    "location": r"(?i)(location|city|state|country|region|address|ciudad)",
    "website": r"(?i)(website|url|domain|web|sitio)",
    "source": r"(?i)(source|channel|origin|lead.?source|referral|fuente)",
    "industry": r"(?i)(industry|sector|vertical|industria)",
    "revenue": r"(?i)(revenue|arr|mrr|budget|size|ingresos)",
    "notes": r"(?i)(notes|comments|description|remarks|notas)",
}


def _auto_map_fields(df: pd.DataFrame, field_types: dict[str, str]) -> dict:
    """Auto-map columns to standard lead field roles."""
    mapping = {}
    used_cols = set()

    for role, pattern in FIELD_ROLE_PATTERNS.items():
        for col in df.columns:
            if col in used_cols:
                continue
            if re.search(pattern, col):
                mapping[role] = col
                used_cols.add(col)
                break

    # Fallback: map by detected type if name-based didn't catch
    if "email" not in mapping:
        for col, dtype in field_types.items():
            if dtype == "email" and col not in used_cols:
                mapping["email"] = col
                used_cols.add(col)
                break

    if "phone" not in mapping:
        for col, dtype in field_types.items():
            if dtype == "phone" and col not in used_cols:
                mapping["phone"] = col
                used_cols.add(col)
                break

    return mapping


# === MAIN DETECTION ===

def detect_leads(df: pd.DataFrame, filename: str = "upload") -> LeadProfile:
    """Analyze a lead DataFrame: detect types, map fields, assess quality.

    PRE: df is a non-empty DataFrame with at least 1 column
    POST: LeadProfile with fields, mapping, quality_score
    INVARIANT: Never modifies the input DataFrame
    """
    if df.empty:
        logger.warning("Empty DataFrame provided")
        return LeadProfile(filename=filename, total_leads=0, quality_score=0.0)

    fields = []
    field_types = {}

    for col in df.columns:
        dtype = _detect_field_type(df[col])
        field_types[col] = dtype
        completeness = df[col].notna().mean()
        sample = df[col].dropna().head(3).tolist()

        fields.append(LeadField(
            name=col,
            dtype=dtype,
            completeness=round(completeness, 3),
            unique_count=df[col].nunique(),
            sample_values=[str(v) for v in sample],
        ))

    mapping = _auto_map_fields(df, field_types)

    # Quality score: weighted by field importance
    weights = {"email": 30, "name": 20, "company": 15, "title": 10, "phone": 10}
    quality = 0.0
    for role, weight in weights.items():
        if role in mapping:
            col = mapping[role]
            comp = df[col].notna().mean()
            quality += comp * weight

    # Add base quality from overall completeness
    base_completeness = df.notna().mean().mean() * 15
    quality = min(100, quality + base_completeness)

    profile = LeadProfile(
        filename=filename,
        total_leads=len(df),
        fields=fields,
        field_mapping=mapping,
        quality_score=round(quality, 1),
    )

    logger.bind(
        service="detector", action="detect",
        total_leads=len(df), fields=len(fields),
        mapped_roles=list(mapping.keys()), quality=profile.quality_score
    ).info("Lead detection complete")

    return profile
