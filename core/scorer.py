"""NoVa LeadScore — AI Scoring Engine.

Batch-scores leads using LLM structured output.
Fallback: rule-based scoring when AI fails (graceful degradation).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from loguru import logger

from config import Config
from providers import call_llm, AIProviderError
from core.detector import LeadProfile


# === DATA MODELS ===

@dataclass
class ScoredLead:
    """Single lead scoring result."""
    row_index: int
    score: int            # 0-100
    priority: str         # Hot / Warm / Cold
    reason: str           # AI-generated explanation
    signals: list[str] = field(default_factory=list)


@dataclass
class ScoreResult:
    """Full scoring output."""
    lead_profile: LeadProfile
    scored_leads: list[ScoredLead] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    scored_at: datetime = field(default_factory=datetime.now)
    ai_used: bool = True
    fallback_used: bool = False


# === SCORING PROMPT ===

SYSTEM_PROMPT = """You are an expert B2B lead scoring analyst. You evaluate leads based on data completeness,
company signals, job title seniority, and engagement indicators.

SCORING RULES:
- 80-100 (Hot): Decision-maker at established company, complete data, strong signals
- 50-79 (Warm): Potential buyer, some data gaps, moderate signals
- 0-49 (Cold): Low intent, missing critical data, weak signals

ALWAYS respond in valid JSON array format. Each element must have exactly these fields:
{"index": int, "score": int, "priority": "Hot"|"Warm"|"Cold", "reason": "1-2 sentence explanation", "signals": ["signal1", "signal2"]}"""


def _build_batch_prompt(df_batch: pd.DataFrame, profile: LeadProfile, start_idx: int) -> str:
    """Build scoring prompt for a batch of leads."""
    field_context = ", ".join(
        f"{role}='{col}'" for role, col in profile.field_mapping.items()
    )

    newline = "\n"
    leads_text = []
    for i, (_, row) in enumerate(df_batch.iterrows()):
        lead_data = {col: str(val) if pd.notna(val) else "MISSING"
                     for col, val in row.items()}
        leads_text.append(f"Lead {start_idx + i}: {json.dumps(lead_data, ensure_ascii=False)}")

    return f"""Score these {len(df_batch)} leads. Field mapping: {field_context}
Data quality: {profile.quality_score}/100

{newline.join(leads_text)}

Return a JSON array with {len(df_batch)} objects. Each: {{"index": <lead_number>, "score": 0-100, "priority": "Hot"/"Warm"/"Cold", "reason": "explanation", "signals": ["signal1"]}}
ONLY return the JSON array, no other text."""


def _parse_ai_scores(response_text: str, batch_size: int, start_idx: int) -> list[ScoredLead]:
    """Parse AI response into ScoredLead objects with validation."""
    # Extract JSON from response (handle markdown code blocks)
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        scores = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in response
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            scores = json.loads(match.group())
        else:
            logger.error("Failed to parse AI response as JSON")
            return []

    if not isinstance(scores, list):
        scores = [scores]

    results = []
    for item in scores:
        try:
            score = max(0, min(100, int(item.get("score", 50))))
            priority = item.get("priority", "Warm")
            if priority not in ("Hot", "Warm", "Cold"):
                priority = "Hot" if score >= 80 else "Warm" if score >= 50 else "Cold"

            results.append(ScoredLead(
                row_index=int(item.get("index", start_idx + len(results))),
                score=score,
                priority=priority,
                reason=str(item.get("reason", "Score based on available data")),
                signals=list(item.get("signals", [])),
            ))
        except (ValueError, TypeError) as e:
            logger.warning(f"Skipping malformed score item: {e}")
            continue

    return results


# === FALLBACK: RULE-BASED SCORING ===

def _rule_based_score(row: pd.Series, profile: LeadProfile) -> ScoredLead:
    """Fallback scoring when AI is unavailable. Based on data completeness."""
    score = 0
    signals = []

    # Completeness score (0-40)
    completeness = row.notna().mean()
    score += int(completeness * 40)
    if completeness > 0.8:
        signals.append("Complete data profile")

    # Email present (+20)
    if "email" in profile.field_mapping:
        col = profile.field_mapping["email"]
        if pd.notna(row.get(col)):
            score += 20
            signals.append("Has email")

    # Company present (+15)
    if "company" in profile.field_mapping:
        col = profile.field_mapping["company"]
        if pd.notna(row.get(col)):
            score += 15
            signals.append("Has company")

    # Title present (+15)
    if "title" in profile.field_mapping:
        col = profile.field_mapping["title"]
        val = str(row.get(col, "")).lower()
        if pd.notna(row.get(col)):
            score += 10
            # Seniority bonus
            senior_keywords = ["ceo", "cto", "cfo", "vp", "director", "head", "chief", "founder", "owner", "president"]
            if any(kw in val for kw in senior_keywords):
                score += 5
                signals.append("Senior title")
            signals.append("Has job title")

    # Phone present (+10)
    if "phone" in profile.field_mapping:
        col = profile.field_mapping["phone"]
        if pd.notna(row.get(col)):
            score += 10
            signals.append("Has phone")

    score = min(100, score)
    priority = "Hot" if score >= 80 else "Warm" if score >= 50 else "Cold"

    return ScoredLead(
        row_index=0,  # set by caller
        score=score,
        priority=priority,
        reason=f"Rule-based: {int(completeness*100)}% complete, {len(signals)} signals",
        signals=signals,
    )


# === MAIN SCORING FUNCTION ===

def score_leads(
    df: pd.DataFrame,
    profile: LeadProfile,
    config: Config,
    progress_callback=None,
) -> ScoreResult:
    """Score all leads in batches. AI primary, rule-based fallback.

    PRE: df non-empty, profile from detect_leads(), config valid
    POST: ScoreResult with scored_leads matching df rows
    INVARIANT: Every lead gets a score (AI or fallback). Never partial.
    """
    result = ScoreResult(lead_profile=profile, scored_at=datetime.now())
    total = len(df)
    ai_available = True

    for batch_start in range(0, total, config.batch_size):
        batch_end = min(batch_start + config.batch_size, total)
        batch_df = df.iloc[batch_start:batch_end]

        if ai_available:
            try:
                prompt = _build_batch_prompt(batch_df, profile, batch_start)
                response = call_llm(
                    prompt=prompt,
                    config=config,
                    system_prompt=SYSTEM_PROMPT,
                    temperature=0.3,
                    max_tokens=4000,
                )
                scored = _parse_ai_scores(response.content, len(batch_df), batch_start)
                result.fallback_used = response.fallback_used

                # Validate: got scores for all leads in batch?
                if len(scored) < len(batch_df):
                    logger.warning(f"AI returned {len(scored)}/{len(batch_df)} scores, filling gaps with rules")
                    scored_indices = {s.row_index for s in scored}
                    for i in range(batch_start, batch_end):
                        if i not in scored_indices:
                            fb = _rule_based_score(df.iloc[i], profile)
                            fb.row_index = i
                            fb.reason = "(Partial AI) " + fb.reason
                            scored.append(fb)

                result.scored_leads.extend(scored)

            except AIProviderError as e:
                logger.error(f"AI scoring failed: {e.what} — switching to rule-based for remaining")
                ai_available = False
                result.ai_used = False
                # Fall through to rule-based below

        if not ai_available:
            for i in range(batch_start, batch_end):
                fb = _rule_based_score(df.iloc[i], profile)
                fb.row_index = i
                result.scored_leads.append(fb)

        if progress_callback:
            progress_callback(batch_end / total)

    # Sort by row_index to maintain order
    result.scored_leads.sort(key=lambda x: x.row_index)

    # Summary
    scores = [s.score for s in result.scored_leads]
    result.summary = {
        "total": total,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "hot": sum(1 for s in result.scored_leads if s.priority == "Hot"),
        "warm": sum(1 for s in result.scored_leads if s.priority == "Warm"),
        "cold": sum(1 for s in result.scored_leads if s.priority == "Cold"),
        "ai_used": result.ai_used,
        "fallback_used": result.fallback_used,
    }

    logger.bind(
        service="scorer", action="score",
        total=total, avg_score=result.summary["avg_score"],
        hot=result.summary["hot"], warm=result.summary["warm"],
        cold=result.summary["cold"], ai_used=result.ai_used
    ).info("Scoring complete")

    return result
