"""
Agent 4: Testing Strategy Agent
---------------------------------
WHAT IT DOES:
  Looks at ALL previous agents' outputs and recommends what tests
  should exist (or are missing) to safely merge this PR.

WHY IT EXISTS:
  The testing strategy depends on EVERYTHING:
    - What changed (Agent 1)
    - What could break (Agent 2)
    - What code issues were found (Agent 3)
  So this agent runs AFTER agents 1, 2, 3 complete.

INPUT (from state):
  - state["change_analysis"]    (Agent 1)
  - state["blast_radius"]       (Agent 2)
  - state["engineering_review"] (Agent 3)
  - state["diff"]
  - state["changed_files"]

OUTPUT (written back to state):
  - state["testing_strategy"]
"""

import json
from core.state import DiffVisionState
from core.fallbacks import infer_testing_strategy, parse_json_response
from core.llm import get_llm


def testing_strategy_agent(state: DiffVisionState) -> DiffVisionState:
    """
    LangGraph node for Testing Strategy Agent.

    This node runs SEQUENTIALLY after the 3 parallel agents.
    It has access to all their outputs via the shared state.
    """
    # Combine previous agent outputs for context
    change_analysis = state.get("change_analysis", {})
    blast_radius = state.get("blast_radius", {})
    engineering_review = state.get("engineering_review", {})
    local_errors: list[str] = []

    prompt = f"""You are a QA lead and senior engineer reviewing a PR's test coverage.

REPOSITORY:
{state["repo_summary"]}

CHANGED FILES:
{chr(10).join(state["changed_files"])}

WHAT CHANGED (Agent 1):
{json.dumps(change_analysis, indent=2)}

BLAST RADIUS (Agent 2):
{json.dumps(blast_radius, indent=2)}

ENGINEERING ISSUES FOUND (Agent 3):
{json.dumps(engineering_review, indent=2)}

DIFF (first 2000 chars):
{state["diff"][:2000]}

Your task: Recommend the tests that should exist BEFORE merging this PR.

Think about:
1. Tests for the changed code itself (unit tests)
2. Integration tests for affected modules from blast radius
3. Edge cases from the engineering review issues
4. Regression tests for existing flows that may break
5. What specifically could go wrong that tests should catch?

Return ONLY valid JSON:
{{
  "missing_tests": [
    "Specific test that should exist, e.g. 'Unit test for UserDTO mapping with null fields'"
  ],
  "edge_cases": [
    "Edge case to test, e.g. 'What happens when userId is negative?'"
  ],
  "regression_risks": [
    "Existing functionality that might regress, e.g. 'Login flow uses getUser() — verify login still works'"
  ],
  "recommended_test_types": ["Unit", "Integration", "Contract", "E2E"],
  "priority_tests": [
    "The 1-3 most critical tests to write first"
  ],
  "test_coverage_assessment": "One of: Likely Adequate, Needs More Tests, Critical Gaps",
  "total_tests_recommended": <integer>
}}

Do NOT include markdown code fences or any text outside the JSON object."""

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        testing_strategy = parse_json_response(response.content)
    except Exception as e:
        testing_strategy = infer_testing_strategy(
            state["changed_files"],
            change_analysis,
            blast_radius,
            engineering_review,
        )
        local_errors.append(f"Agent 4 used heuristic fallback: {e}")

    return {"testing_strategy": testing_strategy, "errors": local_errors}
