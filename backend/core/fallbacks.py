import json
import re
from collections import Counter
from typing import Any


def parse_json_response(content: str) -> dict[str, Any]:
    """Parse JSON responses even if the model wraps them in code fences."""
    cleaned = content.strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]

    return json.loads(cleaned)


def count_changed_lines(diff: str) -> int:
    return sum(
        1
        for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )


def _count_additions_and_deletions(diff: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return any(
        marker in lowered
        for marker in ("/test", "/tests", "\\test", "\\tests", ".spec.", ".test.", "_test.")
    )


def _top_areas(changed_files: list[str], limit: int = 3) -> list[str]:
    areas: list[str] = []

    for raw_path in changed_files:
        parts = [part for part in raw_path.replace("\\", "/").split("/") if part]
        if not parts:
            continue

        if parts[0] in {"src", "app", "lib"} and len(parts) > 1:
            areas.append("/".join(parts[:2]))
        elif parts[0] in {"backend", "frontend", "services", "packages"} and len(parts) > 1:
            areas.append("/".join(parts[:2]))
        elif len(parts) > 1 and parts[0] in {"api", "core", "components"}:
            areas.append("/".join(parts[:2]))
        else:
            areas.append(parts[0])

    if not areas:
        return ["repository root"]

    return [name for name, _ in Counter(areas).most_common(limit)]


def infer_primary_module(changed_files: list[str]) -> str:
    return _top_areas(changed_files, limit=1)[0]


def infer_repository_summary(structure: str, changed_files: list[str]) -> str:
    lowered = structure.lower()
    stack: list[str] = []

    if "fastapi" in lowered or "main.py" in lowered or "requirements.txt" in lowered:
        stack.append("Python/FastAPI")
    elif ".py" in lowered:
        stack.append("Python")

    if "angular.json" in lowered or "app.component.ts" in lowered or "src/main.ts" in lowered:
        stack.append("Angular")
    elif "package.json" in lowered or ".ts" in lowered:
        stack.append("TypeScript")

    if "dockerfile" in lowered or "docker-compose" in lowered:
        stack.append("Docker")

    top_level_modules = []
    for line in structure.splitlines():
        if line.startswith("  "):
            continue
        entry = line.strip().rstrip("/")
        if entry:
            top_level_modules.append(entry)

    top_level_modules = top_level_modules[:5]
    changed_areas = ", ".join(_top_areas(changed_files))

    if "Python/FastAPI" in stack and "Angular" in stack:
        app_type = "a full-stack pull request analysis application"
    elif "Angular" in stack:
        app_type = "a frontend web application"
    elif "Python/FastAPI" in stack:
        app_type = "a backend API service"
    else:
        app_type = "a software application"

    stack_summary = ", ".join(stack) if stack else "mixed project tooling"
    module_summary = ", ".join(top_level_modules) if top_level_modules else "the repository root"

    return (
        f"This repository appears to be {app_type} built with {stack_summary}. "
        f"Top-level modules include {module_summary}, and this PR mainly touches {changed_areas}."
    )


def infer_change_analysis(
    changed_files: list[str],
    diff: str,
    repo_summary: str,
) -> dict[str, Any]:
    file_count = len(changed_files)
    changed_lines = count_changed_lines(diff)
    additions, deletions = _count_additions_and_deletions(diff)
    primary_module = infer_primary_module(changed_files)
    test_only = changed_files and all(_is_test_file(path) for path in changed_files)
    doc_only = changed_files and all(path.lower().endswith((".md", ".rst", ".txt")) for path in changed_files)
    config_files = {
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "package.json",
        "package-lock.json",
        "requirements.txt",
        "pyproject.toml",
        "angular.json",
        "tsconfig.json",
    }
    config_only = changed_files and all(path.split("/")[-1].lower() in config_files for path in changed_files)

    if doc_only:
        change_type = "Documentation"
    elif test_only:
        change_type = "Test Addition"
    elif config_only:
        change_type = "Configuration Change"
    elif any(token in "/".join(changed_files).lower() for token in ("route", "controller", "api", "schema")):
        change_type = "API Contract Change"
    elif additions > deletions * 2 and file_count >= 2:
        change_type = "Feature Addition"
    elif file_count >= 4 and changed_lines >= 120:
        change_type = "Refactoring"
    else:
        change_type = "Bug Fix"

    if changed_lines <= 60 and file_count <= 2:
        complexity = "Low"
    elif changed_lines <= 220 and file_count <= 6:
        complexity = "Medium"
    else:
        complexity = "High"

    key_changes = [path.replace("\\", "/") for path in changed_files[:5]]

    return {
        "summary": (
            f"This PR updates {primary_module} across {file_count} file(s) "
            f"with about {changed_lines} changed line(s)."
        ),
        "change_type": change_type,
        "affected_module": primary_module,
        "complexity": complexity,
        "estimated_lines_changed": changed_lines,
        "business_impact": (
            f"The change affects {primary_module}, which is part of {repo_summary.split('.')[0].lower()}."
        ),
        "key_changes": key_changes,
    }


def infer_blast_radius(
    changed_files: list[str],
    diff: str,
    repo_summary: str,
    change_analysis: dict[str, Any],
) -> dict[str, Any]:
    file_count = len(changed_files)
    changed_lines = count_changed_lines(diff)
    affected_modules = _top_areas(changed_files, limit=5)
    primary_module = change_analysis.get("affected_module") or infer_primary_module(changed_files)
    lowered_paths = " ".join(changed_files).lower()

    if any(token in lowered_paths for token in ("workflow", "context_builder", "main.py", "router", "api")):
        impact_level = "High"
    elif changed_lines > 220 or file_count > 6:
        impact_level = "High"
    elif changed_lines > 80 or file_count > 2:
        impact_level = "Medium"
    else:
        impact_level = "Low"

    dependency_chain: list[str] = []
    user_flows_at_risk: list[str] = []

    if "backend" in lowered_paths or "fastapi" in repo_summary.lower():
        dependency_chain.append("FastAPI route -> context builder -> analysis workflow")
        user_flows_at_risk.append("PR analysis API response flow")

    if "workflow" in lowered_paths or "agent" in lowered_paths:
        dependency_chain.append("Context builder -> agents 1-5 -> merge confidence report")
        user_flows_at_risk.append("End-to-end PR risk analysis pipeline")

    if "frontend" in lowered_paths or "dashboard" in lowered_paths or "angular" in repo_summary.lower():
        dependency_chain.append("Angular dashboard -> analysis service -> backend API")
        user_flows_at_risk.append("Dashboard rendering and report display")

    if not dependency_chain:
        dependency_chain.append(f"{primary_module} -> nearby modules that import or call it")

    user_flows_at_risk = list(dict.fromkeys(user_flows_at_risk))
    downstream_estimate = {"Low": 1, "Medium": 3, "High": 5, "Critical": 7}[impact_level]

    return {
        "affected_modules": affected_modules,
        "impact_level": impact_level,
        "reasoning": (
            f"The change touches {primary_module}, so anything depending on those files may need retesting. "
            f"Given the diff size and touched areas, the likely blast radius is {impact_level.lower()}."
        ),
        "dependency_chain": dependency_chain,
        "user_flows_at_risk": user_flows_at_risk,
        "estimated_downstream_services": downstream_estimate,
    }


def infer_engineering_review(diff: str, changed_files: list[str]) -> dict[str, Any]:
    lowered = diff.lower()
    changed_lines = count_changed_lines(diff)
    security: list[str] = []
    performance: list[str] = []
    maintainability: list[str] = []
    code_quality: list[str] = []
    positive_notes: list[str] = []

    if any(token in lowered for token in ("eval(", "exec(", "shell=true", "password", "secret", "token")):
        security.append("Review secret handling and unsafe execution paths introduced in the diff.")

    if "except Exception" in diff or "catch (err" in lowered:
        code_quality.append("Broad exception handling was changed; verify that failures still surface with enough context.")

    if "print(" in diff or "console.log(" in diff:
        code_quality.append("Debug logging appears in the diff and should be trimmed before merge.")

    if "todo" in lowered or "fixme" in lowered:
        maintainability.append("The diff includes TODO/FIXME markers that may leave follow-up work unresolved.")

    if changed_lines > 220:
        maintainability.append("This is a relatively large diff; consider smaller follow-up slices if review confidence is low.")

    if len(changed_files) > 5:
        performance.append("Cross-cutting changes increase coordination cost; re-check hot paths touched by multiple files.")

    if any(_is_test_file(path) for path in changed_files):
        positive_notes.append("The PR updates tests alongside code changes, which improves merge confidence.")

    if any(path.lower().endswith((".py", ".ts")) for path in changed_files):
        positive_notes.append("The changed files keep implementation scoped to typed source files, which helps maintainability.")

    total_issues_found = len(security) + len(performance) + len(maintainability) + len(code_quality)

    if security:
        overall_severity = "High"
    elif total_issues_found >= 4:
        overall_severity = "Medium"
    else:
        overall_severity = "Low"

    return {
        "security": security,
        "performance": performance,
        "maintainability": maintainability,
        "code_quality": code_quality,
        "overall_severity": overall_severity,
        "positive_notes": positive_notes,
        "total_issues_found": total_issues_found,
    }


def infer_testing_strategy(
    changed_files: list[str],
    change_analysis: dict[str, Any],
    blast_radius: dict[str, Any],
    engineering_review: dict[str, Any],
) -> dict[str, Any]:
    missing_tests: list[str] = []
    edge_cases: list[str] = []
    regression_risks: list[str] = []
    recommended_types: list[str] = []

    lowered_paths = " ".join(changed_files).lower()
    changed_tests = any(_is_test_file(path) for path in changed_files)

    if "main.py" in lowered_paths or "api" in lowered_paths:
        missing_tests.append("API smoke test covering the main PR analysis endpoint and error responses.")
        recommended_types.extend(["Integration", "E2E"])

    if "workflow" in lowered_paths or "agent" in lowered_paths:
        missing_tests.append("Workflow smoke test that exercises all analysis agents and confidence score generation.")
        regression_risks.append("The LangGraph pipeline could stop early or skip an agent if orchestration changed.")
        recommended_types.extend(["Unit", "Integration"])

    if "context_builder" in lowered_paths:
        missing_tests.append("Context builder test for PR URL parsing, GitHub fetch, and repository summary fallback behavior.")
        edge_cases.append("Public PR analysis without API keys should still return a structured report.")
        recommended_types.append("Unit")

    if "frontend" in lowered_paths or "dashboard" in lowered_paths or "app.ts" in lowered_paths:
        missing_tests.append("Frontend rendering test for idle, loading, success, and error states.")
        regression_risks.append("The dashboard can fail if result bindings or guards are out of sync.")
        recommended_types.extend(["Unit", "E2E"])

    if engineering_review.get("security"):
        edge_cases.append("Validate failure paths and malformed inputs around the risky code paths called out in the review.")
    if engineering_review.get("code_quality"):
        edge_cases.append("Exercise fallback and exception paths so error handling changes do not hide failures.")

    if not changed_tests:
        regression_risks.append("No tests changed with the implementation, so important paths may not be covered yet.")

    impact_level = (blast_radius.get("impact_level") or "Unknown").lower()
    complexity = (change_analysis.get("complexity") or "Unknown").lower()

    if not changed_tests and (impact_level in {"high", "critical"} or complexity == "high"):
        assessment = "Critical Gaps"
    elif not changed_tests:
        assessment = "Needs More Tests"
    else:
        assessment = "Likely Adequate"

    recommended_types = list(dict.fromkeys(recommended_types or ["Unit"]))
    missing_tests = list(dict.fromkeys(missing_tests))
    edge_cases = list(dict.fromkeys(edge_cases or ["Invalid PR URL should return a clear validation error."]))
    regression_risks = list(dict.fromkeys(regression_risks))
    priority_tests = (missing_tests or regression_risks or edge_cases)[:3]

    return {
        "missing_tests": missing_tests,
        "edge_cases": edge_cases,
        "regression_risks": regression_risks,
        "recommended_test_types": recommended_types,
        "priority_tests": priority_tests,
        "test_coverage_assessment": assessment,
        "total_tests_recommended": len(missing_tests) + len(edge_cases),
    }


def build_confidence_summary(
    score_data: dict[str, Any],
    change_analysis: dict[str, Any],
    blast_radius: dict[str, Any],
    engineering_review: dict[str, Any],
    testing_strategy: dict[str, Any],
) -> str:
    module = change_analysis.get("affected_module", "the changed area")
    recommendation = score_data["recommendation"]
    impact_level = blast_radius.get("impact_level", "unknown").lower()
    severity = engineering_review.get("overall_severity", "unknown").lower()
    testing = testing_strategy.get("test_coverage_assessment", "unknown")
    actions = testing_strategy.get("priority_tests", [])[:2]

    action_text = "; ".join(actions) if actions else "add a focused smoke test before merging"

    return (
        f"{recommendation} for {module}. "
        f"The current score reflects {impact_level} blast-radius risk, {severity} engineering concerns, "
        f"and a testing posture assessed as {testing.lower()}. "
        f"Before merging, {action_text}."
    )
