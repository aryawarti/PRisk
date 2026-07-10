"""
Agent 3: Engineering Review Agent
-----------------------------------
WHAT IT DOES:
  Performs a senior engineer's code review across 4 dimensions:
    - Security  : input validation, auth checks, injection risks
    - Performance: N+1 queries, missing caches, expensive loops
    - Maintainability: method size, naming, coupling
    - Code Quality: duplication, dead code, missing error handling

WHY IT EXISTS:
  This gives developers actionable feedback beyond "does it work?"
  It answers: "Is this the RIGHT way to do it?"

INPUT (from state):
  - state["diff"]
  - state["changed_files"]
  - state["repo_summary"]

OUTPUT (written back to state):
  - state["engineering_review"]
"""

import json
from core.state import PRiskState
from core.fallbacks import infer_engineering_review
from core.llm import invoke_llm_json


MAX_DIFF_CHARS = 5000    # Give this agent a bit more context since it's reading code


def engineering_review_agent(state: PRiskState) -> PRiskState:
    """
    LangGraph node function for the Engineering Review Agent.

    This agent runs in PARALLEL with Agent 1 and Agent 2.
    LangGraph manages this automatically using the graph definition in workflow.py.
    """
    diff_text = state["diff"][:MAX_DIFF_CHARS]
    local_errors: list[str] = []

    prompt = f"""You are a senior software engineer doing a thorough code review.

REPOSITORY:
{state["repo_summary"]}

CHANGED FILES:
{chr(10).join(state["changed_files"])}

CODE CHANGES (diff):
{diff_text}

Review this PR across 4 dimensions and return a JSON report.

For each issue, be SPECIFIC — mention the actual method name, variable, or line pattern.
Do NOT invent issues that don't exist in the diff.
If a category has no issues, return an empty list for it.

Each finding is an OBJECT with three keys:
  "text"     — the specific issue
  "severity" — one of: Critical, High, Medium, Low
  "effort"   — one of: "Quick fix" (mechanical, <15 min) or "Needs thought" (design decision required)

Return ONLY valid JSON:
{{
  "security": [
    {{"text": "userId from request body used in SQL query without sanitisation", "severity": "Critical", "effort": "Quick fix"}}
  ],
  "performance": [
    {{"text": "getOrders() called inside for-loop — potential N+1 query", "severity": "Medium", "effort": "Needs thought"}}
  ],
  "maintainability": [
    {{"text": "processPayment() is 180 lines — should be split", "severity": "Low", "effort": "Needs thought"}}
  ],
  "code_quality": [
    {{"text": "Null check duplicated in 3 places — extract to helper", "severity": "Low", "effort": "Quick fix"}}
  ],
  "overall_severity": "One of: Low, Medium, High, Critical",
  "positive_notes": [
    "What was done well in this PR (be specific)"
  ],
  "total_issues_found": <integer>
}}

Do NOT include markdown code fences or any text outside the JSON object."""

    try:
        engineering_review = invoke_llm_json(
            prompt,
            required_keys=("security", "performance", "maintainability", "code_quality", "overall_severity"),
        )
    except Exception as e:
        engineering_review = infer_engineering_review(state["diff"], state["changed_files"])
        local_errors.append(f"Agent 3 used heuristic fallback: {e}")

    return {"engineering_review": engineering_review, "errors": local_errors}
