"""NoVa LeadScore — Smoke Test (no API key needed).

Tests the full pipeline with mock data and rule-based scoring.
Run: python smoke_test.py
"""

import sys
import os
from pathlib import Path

# Ensure no API key for pure rule-based test
os.environ.pop("GOOGLE_AI_API_KEY", None)
os.environ.pop("LLM_API_KEY", None)
os.environ["LLM_MODEL"] = "gemini/gemini-2.5-flash"

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from config import get_config
from core.detector import detect_leads
from core.scorer import score_leads
from validate import validate_dataframe


def test_detector():
    """Test field detection and mapping."""
    print("TEST 1: Field Detection + Mapping")
    df = pd.read_csv("sample_leads.csv")

    profile = detect_leads(df, "sample_leads.csv")

    assert profile.total_leads == 10, f"Expected 10 leads, got {profile.total_leads}"
    assert len(profile.fields) == 8, f"Expected 8 fields, got {len(profile.fields)}"
    assert "email" in profile.field_mapping, "Should detect email column"
    assert "name" in profile.field_mapping, "Should detect name column"
    assert "company" in profile.field_mapping, "Should detect company column"
    assert profile.quality_score > 0, "Quality score should be > 0"

    print(f"  ✅ {profile.total_leads} leads, {len(profile.fields)} fields")
    print(f"  ✅ Mapped: {profile.field_mapping}")
    print(f"  ✅ Quality: {profile.quality_score}/100")
    return profile, df


def test_scorer(profile, df):
    """Test scoring (rule-based fallback — no API key)."""
    print("\nTEST 2: Rule-Based Scoring (no API key)")
    config = get_config()

    result = score_leads(df, profile, config)

    assert len(result.scored_leads) == 10, f"Expected 10 scored leads, got {len(result.scored_leads)}"
    assert not result.ai_used, "Should use rule-based (no API key)"

    for sl in result.scored_leads:
        assert 0 <= sl.score <= 100, f"Score out of range: {sl.score}"
        assert sl.priority in ("Hot", "Warm", "Cold"), f"Invalid priority: {sl.priority}"
        assert sl.reason, "Should have reason"

    s = result.summary
    assert s["total"] == 10
    assert s["hot"] + s["warm"] + s["cold"] == 10

    print("  ✅ All 10 leads scored (rule-based)")
    print(f"  ✅ Avg: {s['avg_score']}, Hot: {s['hot']}, Warm: {s['warm']}, Cold: {s['cold']}")
    return result


def test_validation():
    """Test input validation."""
    print("\nTEST 3: Input Validation")

    # Empty DataFrame
    ok, errs = validate_dataframe(pd.DataFrame())
    assert not ok, "Should reject empty DataFrame"
    print("  ✅ Empty DataFrame rejected")

    # Too many leads
    big_df = pd.DataFrame({"a": range(600), "b": range(600)})
    ok, errs = validate_dataframe(big_df, max_leads=500)
    assert not ok, "Should reject >500 leads"
    print("  ✅ Over-limit leads rejected")

    # Valid DataFrame
    ok, errs = validate_dataframe(pd.read_csv("sample_leads.csv"))
    assert ok, f"Should accept valid CSV: {errs}"
    print("  ✅ Valid CSV accepted")


def test_export(result, df):
    """Test CSV/Excel export."""
    print("\nTEST 4: Export")
    export_data = []
    for sl in result.scored_leads:
        row = df.iloc[sl.row_index].to_dict() if sl.row_index < len(df) else {}
        row["LeadScore"] = sl.score
        row["Priority"] = sl.priority
        row["AI_Reason"] = sl.reason
        export_data.append(row)

    export_df = pd.DataFrame(export_data)
    assert "LeadScore" in export_df.columns, "Should have LeadScore column"
    assert "Priority" in export_df.columns, "Should have Priority column"
    assert len(export_df) == 10, f"Expected 10 rows, got {len(export_df)}"
    print(f"  ✅ Export DataFrame: {len(export_df)} rows, {len(export_df.columns)} columns")


if __name__ == "__main__":
    print("=" * 50)
    print("NoVa LeadScore — Smoke Test")
    print("=" * 50)

    try:
        profile, df = test_detector()
        result = test_scorer(profile, df)
        test_validation()
        test_export(result, df)

        print("\n" + "=" * 50)
        print("✅ ALL TESTS PASSED")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
