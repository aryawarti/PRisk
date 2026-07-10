"""
Agent 5: Merge Confidence Agent
---------------------------------
THE FINAL DECISION MAKER.

The score itself is computed by core/scoring.py — a deterministic,
evidence-blended engine (see that module for the full methodology).
No LLM participates in the arithmetic; this agent's only AI task is
writing the executive summary, and it writes it FROM the computed
drivers so the narrative can never contradict the number.

Weights (product identity, unchanged):
  Blast Radius 40 · Engineering 30 · Testing 20 · Complexity 10

Recommendation bands: 80–100 Safe to Merge · 60–79 Needs Validation · <60 Do Not Merge
"""

import json

from core.state import PRiskState
from core.fallbacks import build_confidence_summary
from core.llm import invoke_llm_text
from core.scoring import compute_confidence


def merge_confidence_agent(state: PRiskState) -> PRiskState:
    """
    Step 1: Deterministic score + per-dimension drivers (core/scoring.py).
    Step 2: LLM writes a summary grounded in those exact drivers.
    """
    blast_radius = state.get("blast_radius", {})
    engineering_review = state.get("engineering_review", {})
    testing_strategy = state.get("testing_strategy", {})
    change_analysis = state.get("change_analysis", {})
    history_risk = state.get("history_risk", {})
    local_errors: list[str] = []

    # Step 1: deterministic scoring with provenance
    score_data = compute_confidence(
        blast_radius=blast_radius,
        engineering_review=engineering_review,
        testing_strategy=testing_strategy,
        change_analysis=change_analysis,
        history_risk=history_risk,
        changed_files=state.get("changed_files", []),
        diff=state.get("diff", ""),
    )

    # Step 2: LLM summary grounded in the computed drivers
    prompt = f"""You are a senior engineering lead writing a final PR review summary.

The confidence score was computed deterministically. Here is EXACTLY why:

SCORE: {score_data["score"]}/100 → {score_data["recommendation"]}

BREAKDOWN AND DRIVERS (negative points = confidence lost):
{json.dumps(score_data["score_drivers"], indent=2)}

CONTEXT:
Change: {json.dumps(change_analysis)[:600]}
Blast radius reasoning: {str(blast_radius.get("reasoning", ""))[:400]}
Top priority tests: {json.dumps(testing_strategy.get("priority_tests", []))[:400]}

Write a 3-4 sentence executive summary that:
1. States the recommendation clearly
2. Explains the score using ONLY the drivers listed above — do not invent factors
3. Gives 1-2 concrete actions that would most improve the score before merging

Be direct and specific. Use actual module/service names from the context.
Output ONLY the summary text, nothing else."""

    try:
        executive_summary = invoke_llm_text(prompt)
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
