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
from core.fallbacks import infer_engineering_review, parse_json_response
from core.llm import get_llm


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

Return ONLY valid JSON:
{{
  "security": [
    "Specific security issue found, e.g. 'userId from request body is used in SQL query without sanitisation'"
  ],
  "performance": [
    "Specific performance issue, e.g. 'getOrders() called inside for-loop — potential N+1 query'"
  ],
  "maintainability": [
    "Specific maintainability issue, e.g. 'processPayment() is 180 lines — should be split'"
  ],
  "code_quality": [
    "Specific quality issue, e.g. 'Null check duplicated in 3 places — extract to helper'"
  ],
  "overall_severity": "One of: Low, Medium, High, Critical",
  "positive_notes": [
    "What was done well in this PR (be specific)"
  ],
  "total_issues_found": <integer>
}}

Do NOT include markdown code fences or any text outside the JSON object."""

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        engineering_review = parse_json_response(response.content)
    except Exception as e:
        engineering_review = infer_engineering_review(state["diff"], state["changed_files"])
        local_errors.append(f"Agent 3 used heuristic fallback: {e}")

    return {"engineering_review": engineering_review, "errors": local_errors}
