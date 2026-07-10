"""
Agent 2: Blast Radius Agent
----------------------------
THE MOST IMPORTANT AGENT. This is what makes PRisk unique.

WHAT IT DOES:
  Analyses the changed files, scans the diff for class/method names,
  then reasons about what other parts of the codebase depend on those
  changed components. Estimates the "blast radius" — how many things
  could break if this PR is merged with a bug.

WHY IT'S UNIQUE:
  Most code review tools look at what changed.
  PRisk looks at what DEPENDS on what changed.

  Example: UserService.getUser() changes → who calls this?
    → UserController, OrderService, NotificationService all call it.
    → Blast radius is HIGH.

INPUT (from state):
  - state["diff"]
  - state["changed_files"]
  - state["repo_summary"]
  - state["change_analysis"]   ← uses Agent 1's output

OUTPUT (written back to state):
  - state["blast_radius"]
"""

import json
from core.state import PRiskState
from core.fallbacks import infer_change_analysis
from core.llm import AnalysisUnavailable, LLMUnavailable, invoke_llm_json


MAX_DIFF_CHARS = 4000


def blast_radius_agent(state: PRiskState) -> PRiskState:
    """
    LangGraph node function for the Blast Radius Agent.

    Strategy:
      We give the LLM the diff, the repository structure summary, and
      the change analysis. We ask it to reason about dependencies and
      estimate how widely the change could ripple.

      In a V2, we'd do static analysis (import graph, call graph) here.
      For the MVP, LLM reasoning is surprisingly good at this.
    """
    diff_text = state["diff"][:MAX_DIFF_CHARS]
    local_errors: list[str] = []
    change_analysis = state.get("change_analysis") or infer_change_analysis(
        state["changed_files"],
        state["diff"],
        state["repo_summary"],
    )

    # Evidence from git history (mined by context_builder). A file with a
    # track record of fixes/reverts is empirically riskier to change.
    history_risk = state.get("history_risk") or {}
    history_section = ""
    if history_risk.get("available") and history_risk.get("files"):
        history_section = f"""

HISTORICAL RISK EVIDENCE (mined from the last {history_risk.get("window_commits", 0)} commits):
{json.dumps(history_risk.get("files", []), indent=2)}
Files listed with high "fix_commits" have repeatedly needed bug fixes or reverts —
weigh them as empirically fragile when estimating impact_level."""

    prompt = f"""You are a senior software architect performing a blast radius analysis.

REPOSITORY:
{state["repo_summary"]}

CHANGED FILES:
{chr(10).join(state["changed_files"])}

    OPTIONAL CHANGE SUMMARY:
{json.dumps(change_analysis, indent=2)}
{history_section}

DIFF EXCERPT:
{diff_text}

Your task: Identify which modules, services, or classes might be IMPACTED by
this change — things that call, import, extend, or depend on the changed code.

Think step-by-step:
1. What classes/functions/APIs were changed?
2. Who typically calls or imports those in a {state["repo_summary"][:80]} type project?
3. What downstream systems or user flows could be affected?

Return ONLY valid JSON with these exact keys:
{{
  "affected_modules": ["list of class/service/module names that may be impacted"],
  "impact_level": "One of: Low, Medium, High, Critical",
  "reasoning": "2-3 sentences explaining why these modules are affected",
  "dependency_chain": ["e.g. UserService -> OrderService -> PaymentService"],
  "user_flows_at_risk": ["e.g. Login flow", "Checkout flow"],
  "estimated_downstream_services": <integer number of potentially affected services>
}}

Do NOT include markdown code fences or any text outside the JSON object."""

    # STRICT MODE: abort with a clear reason instead of guessing.
    try:
        blast_radius = invoke_llm_json(
            prompt,
            required_keys=("affected_modules", "impact_level", "reasoning"),
        )
    except LLMUnavailable as e:
        raise AnalysisUnavailable(str(e)) from e

    return {"blast_radius": blast_radius, "errors": local_errors}
