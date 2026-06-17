"""
Agent 5: Merge Confidence Agent
---------------------------------
THE FINAL DECISION MAKER.

WHAT IT DOES:
  Combines all 4 previous agents' outputs into a single score (0-100)
  with a recommendation: Safe to Merge / Needs Validation / Do Not Merge.

SCORING FORMULA:
  Blast Radius  → 40% of score
  Engineering   → 30% of score
  Testing       → 20% of score
  Complexity    → 10% of score

  IMPORTANT: A higher score = HIGHER confidence = SAFER to merge.
  A low score means "risky, don't merge yet."

  Blast Radius scoring:
    Low/None       → 40 pts
    Medium         → 25 pts
    High           → 15 pts
    Critical       → 0 pts

  Engineering scoring:
    Low severity   → 30 pts
    Medium         → 20 pts
    High           → 10 pts
    Critical       → 0 pts

  Testing scoring:
    Likely Adequate → 20 pts
    Needs More      → 12 pts
    Critical Gaps   → 0 pts

  Complexity scoring:
    Low            → 10 pts
    Medium         → 7 pts
    High           → 3 pts

RECOMMENDATION:
  80-100 → Safe to Merge
  60-79  → Needs Validation
  0-59   → Do Not Merge

INPUT (from state): All 4 agents' outputs
OUTPUT: state["confidence_report"]
"""

import json
from core.state import PRiskState
from core.fallbacks import build_confidence_summary
from core.llm import get_llm


# ── Pure Python scoring (no LLM needed) ──────────────────────────────────────

BLAST_SCORES = {
    "low": 40, "none": 40,
    "medium": 25,
    "high": 15,
    "critical": 0,
    "unknown": 20,
}

ENGINEERING_SCORES = {
    "low": 30,
    "medium": 20,
    "high": 10,
    "critical": 0,
    "unknown": 15,
}

TESTING_SCORES = {
    "likely adequate": 20,
    "needs more tests": 12,
    "critical gaps": 0,
    "unknown": 10,
}

COMPLEXITY_SCORES = {
    "low": 10,
    "medium": 7,
    "high": 3,
    "unknown": 5,
}


def calculate_confidence_score(
    blast_radius: dict,
    engineering_review: dict,
    testing_strategy: dict,
    change_analysis: dict,
) -> dict:
    """
    Pure Python scoring — deterministic, no LLM needed.
    Returns the full breakdown dict.
    """

    # Get impact levels from each agent (lowercase for lookup)
    blast_level = blast_radius.get("impact_level", "unknown").lower()
    eng_severity = engineering_review.get("overall_severity", "unknown").lower()
    test_assessment = testing_strategy.get("test_coverage_assessment", "unknown").lower()
    complexity = change_analysis.get("complexity", "unknown").lower()

    # Calculate component scores
    blast_score = BLAST_SCORES.get(blast_level, 20)
    eng_score = ENGINEERING_SCORES.get(eng_severity, 15)
    test_score = TESTING_SCORES.get(test_assessment, 10)
    complexity_score = COMPLEXITY_SCORES.get(complexity, 5)

    total = blast_score + eng_score + test_score + complexity_score

    # Map score to recommendation
    if total >= 80:
        recommendation = "Safe to Merge"
        recommendation_color = "green"
    elif total >= 60:
        recommendation = "Needs Validation"
        recommendation_color = "amber"
    else:
        recommendation = "Do Not Merge"
        recommendation_color = "red"

    return {
        "score": total,
        "recommendation": recommendation,
        "recommendation_color": recommendation_color,
        "breakdown": {
            "blast_radius_score": blast_score,
            "blast_radius_max": 40,
            "engineering_score": eng_score,
            "engineering_max": 30,
            "testing_score": test_score,
            "testing_max": 20,
            "complexity_score": complexity_score,
            "complexity_max": 10,
        },
        "input_levels": {
            "blast_radius_level": blast_level,
            "engineering_severity": eng_severity,
            "testing_assessment": test_assessment,
            "complexity": complexity,
        },
    }


def merge_confidence_agent(state: PRiskState) -> PRiskState:
    """
    LangGraph node for the Merge Confidence Agent.

    Step 1: Calculate numeric score with pure Python formula.
    Step 2: Ask LLM to write a human-readable summary that explains
            the score in context of the specific PR.
    """
    blast_radius = state.get("blast_radius", {})
    engineering_review = state.get("engineering_review", {})
    testing_strategy = state.get("testing_strategy", {})
    change_analysis = state.get("change_analysis", {})
    local_errors: list[str] = []

    # Step 1: Pure Python scoring
    score_data = calculate_confidence_score(
        blast_radius, engineering_review, testing_strategy, change_analysis
    )

    # Step 2: LLM writes a human-readable summary
    prompt = f"""You are a senior engineering lead writing a final PR review summary.

PR ANALYSIS RESULTS:

Change Analysis:
{json.dumps(change_analysis, indent=2)}

Blast Radius:
{json.dumps(blast_radius, indent=2)}

Engineering Review:
{json.dumps(engineering_review, indent=2)}

Testing Strategy:
{json.dumps(testing_strategy, indent=2)}

CALCULATED CONFIDENCE SCORE: {score_data["score"]}/100
RECOMMENDATION: {score_data["recommendation"]}

Write a 3-4 sentence executive summary that:
1. States the recommendation clearly
2. Explains the main risk factors
3. Gives 1-2 concrete actions the developer should take before merging

Be direct and specific. Use the actual module/service names from the analysis.
Output ONLY the summary text, nothing else."""

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        executive_summary = response.content.strip()
    except Exception as e:
        executive_summary = build_confidence_summary(
            score_data,
            change_analysis,
            blast_radius,
            engineering_review,
            testing_strategy,
        )
        local_errors.append(f"Agent 5 used summary fallback: {e}")

    # Merge everything into the final report
    all_errors = state.get("errors", []) + local_errors
    confidence_report = {
        **score_data,
        "executive_summary": executive_summary,
        "errors_during_analysis": all_errors,
    }

    return {"confidence_report": confidence_report, "errors": local_errors}
