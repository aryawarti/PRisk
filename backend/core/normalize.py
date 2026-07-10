"""
Agent Output Normalization
--------------------------
LLM responses are parsed JSON — the model can omit keys, return strings
where we expect integers, or return a string where we expect a list.
The frontend binds directly to these shapes, so a single missing key
would crash the dashboard.

Every agent output passes through these normalizers before it is
serialized into the API response. Guarantees:
  - every expected key exists
  - lists are lists of strings
  - integers are integers
  - enum-ish fields fall back to a sane default
"""

from typing import Any


def _as_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return int(digits)
    return default


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        items = []
        for item in value:
            text = _as_str(item)
            if text:
                items.append(text)
        return items
    return []


def _as_enum(value: Any, allowed: list[str], default: str) -> str:
    text = _as_str(value)
    for option in allowed:
        if text.lower() == option.lower():
            return option
    return default


def normalize_change_analysis(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    return {
        "summary": _as_str(data.get("summary"), "No summary available."),
        "change_type": _as_str(data.get("change_type"), "Unknown"),
        "affected_module": _as_str(data.get("affected_module"), "Unknown"),
        "complexity": _as_enum(data.get("complexity"), ["Low", "Medium", "High"], "Medium"),
        "estimated_lines_changed": _as_int(data.get("estimated_lines_changed")),
        "business_impact": _as_str(data.get("business_impact")),
        "key_changes": _as_str_list(data.get("key_changes")),
    }


def normalize_blast_radius(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    return {
        "affected_modules": _as_str_list(data.get("affected_modules")),
        "impact_level": _as_enum(
            data.get("impact_level"), ["Low", "Medium", "High", "Critical"], "Medium"
        ),
        "reasoning": _as_str(data.get("reasoning")),
        "dependency_chain": _as_str_list(data.get("dependency_chain")),
        "user_flows_at_risk": _as_str_list(data.get("user_flows_at_risk")),
        "estimated_downstream_services": _as_int(data.get("estimated_downstream_services")),
    }


def normalize_engineering_review(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    security = _as_str_list(data.get("security"))
    performance = _as_str_list(data.get("performance"))
    maintainability = _as_str_list(data.get("maintainability"))
    code_quality = _as_str_list(data.get("code_quality"))
    total = data.get("total_issues_found")
    return {
        "security": security,
        "performance": performance,
        "maintainability": maintainability,
        "code_quality": code_quality,
        "overall_severity": _as_enum(
            data.get("overall_severity"), ["Low", "Medium", "High", "Critical"], "Medium"
        ),
        "positive_notes": _as_str_list(data.get("positive_notes")),
        "total_issues_found": _as_int(
            total, len(security) + len(performance) + len(maintainability) + len(code_quality)
        ),
    }


def normalize_testing_strategy(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    missing_tests = _as_str_list(data.get("missing_tests"))
    edge_cases = _as_str_list(data.get("edge_cases"))
    return {
        "missing_tests": missing_tests,
        "edge_cases": edge_cases,
        "regression_risks": _as_str_list(data.get("regression_risks")),
        "recommended_test_types": _as_str_list(data.get("recommended_test_types")) or ["Unit"],
        "priority_tests": _as_str_list(data.get("priority_tests")),
        "test_coverage_assessment": _as_enum(
            data.get("test_coverage_assessment"),
            ["Likely Adequate", "Needs More Tests", "Critical Gaps"],
            "Needs More Tests",
        ),
        "total_tests_recommended": _as_int(
            data.get("total_tests_recommended"), len(missing_tests) + len(edge_cases)
        ),
    }


def normalize_confidence_report(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    breakdown = data.get("breakdown") if isinstance(data.get("breakdown"), dict) else {}
    input_levels = data.get("input_levels") if isinstance(data.get("input_levels"), dict) else {}
    return {
        "score": max(0, min(100, _as_int(data.get("score")))),
        "recommendation": _as_str(data.get("recommendation"), "Needs Validation"),
        "recommendation_color": _as_enum(
            data.get("recommendation_color"), ["green", "amber", "red"], "amber"
        ),
        "executive_summary": _as_str(data.get("executive_summary")),
        "errors_during_analysis": _as_str_list(data.get("errors_during_analysis")),
        "breakdown": {
            "blast_radius_score": _as_int(breakdown.get("blast_radius_score")),
            "blast_radius_max": _as_int(breakdown.get("blast_radius_max"), 40),
            "engineering_score": _as_int(breakdown.get("engineering_score")),
            "engineering_max": _as_int(breakdown.get("engineering_max"), 30),
            "testing_score": _as_int(breakdown.get("testing_score")),
            "testing_max": _as_int(breakdown.get("testing_max"), 20),
            "complexity_score": _as_int(breakdown.get("complexity_score")),
            "complexity_max": _as_int(breakdown.get("complexity_max"), 10),
        },
        "input_levels": {
            "blast_radius_level": _as_str(input_levels.get("blast_radius_level"), "unknown"),
            "engineering_severity": _as_str(input_levels.get("engineering_severity"), "unknown"),
            "testing_assessment": _as_str(input_levels.get("testing_assessment"), "unknown"),
            "complexity": _as_str(input_levels.get("complexity"), "unknown"),
        },
    }
