"""
Agent 1: Change Understanding Agent
------------------------------------
WHAT IT DOES:
  Reads the diff and changed files, then explains what changed, why,
  which business module was affected, and how complex the change is.

WHY IT EXISTS:
  Before any risk analysis can happen, we need to understand what
  actually changed. This gives every subsequent agent a clean, structured
  picture instead of raw diff text.

INPUT (from state):
  - state["diff"]           : The raw unified diff
  - state["changed_files"]  : List of file paths
  - state["repo_summary"]   : Plain-English repo description

OUTPUT (written back to state):
  - state["change_analysis"] : dict with summary, type, module, complexity
"""
import json
from core.state import PRiskState
from core.llm import AnalysisUnavailable, LLMUnavailable, invoke_llm_json


# Limit diff length sent to LLM to avoid token overflows.
# 4000 chars ≈ ~1000 tokens, enough to understand most diffs.
MAX_DIFF_CHARS = 4000


def change_understanding_agent(state: PRiskState) -> PRiskState:
    """
    LangGraph node function. Receives state, returns updated state.

    LangGraph calls this function automatically when it's the node's turn.
    The return value is MERGED into the existing state (not replaced).
    So we only need to return the key we're changing.
    """
    local_errors: list[str] = []

    # Truncate diff if it's massive
    diff_text = state["diff"][:MAX_DIFF_CHARS]
    if len(state["diff"]) > MAX_DIFF_CHARS:
        diff_text += "\n... [diff truncated for brevity]"

    # Build prompt with all context
    prompt = f"""You are a senior software engineer performing a pull request analysis.

REPOSITORY CONTEXT:
{state["repo_summary"]}

CHANGED FILES:
{chr(10).join(state["changed_files"])}

DIFF:
{diff_text}

Your task: Analyse what changed in this PR and return a JSON object.

Return ONLY valid JSON with these exact keys:
{{
  "summary": "One sentence describing what changed",
  "change_type": "One of: Bug Fix, Feature Addition, Refactoring, API Contract Change, Configuration Change, Test Addition, Documentation",
  "affected_module": "Which business module/package is primarily affected",
  "complexity": "One of: Low, Medium, High",
  "estimated_lines_changed": <integer>,
  "business_impact": "One sentence on business significance",
  "key_changes": ["list", "of", "key", "individual", "changes", "max 5 items"]
}}

Do NOT include markdown code fences or any text outside the JSON object."""

    # STRICT MODE: no heuristic fallback. If the AI can't run, the analysis
    # aborts with a clear reason — PRisk never presents guesses as results.
    try:
        change_analysis = invoke_llm_json(
            prompt,
            required_keys=("summary", "change_type", "complexity"),
        )
    except LLMUnavailable as e:
        raise AnalysisUnavailable(str(e)) from e

    return {"change_analysis": change_analysis, "errors": local_errors}
