"""Normalization: garbage in, guaranteed shape out — the frontend's safety net."""

from core.normalize import (
    normalize_blast_radius,
    normalize_change_analysis,
    normalize_confidence_report,
    normalize_dependency_evidence,
    normalize_engineering_review,
    normalize_history_risk,
    normalize_testing_strategy,
)


def test_change_analysis_from_garbage():
    result = normalize_change_analysis(
        {"complexity": "HIGH", "estimated_lines_changed": "about 40 lines", "key_changes": "one string"}
    )
    assert result["complexity"] == "High"
    assert result["estimated_lines_changed"] == 40
    assert result["key_changes"] == ["one string"]
    assert result["summary"]  # default filled in


def test_change_analysis_from_none():
    result = normalize_change_analysis(None)
    for key in ("summary", "change_type", "affected_module", "complexity", "key_changes"):
        assert key in result


def test_engineering_accepts_strings_and_objects():
    result = normalize_engineering_review(
        {
            "security": ["SQL injection in getUser"],
            "code_quality": [{"text": "dup null check", "severity": "low", "effort": "Quick fix"}],
            "overall_severity": "High",
        }
    )
    assert result["security"][0]["severity"] == "High"  # security defaults high
    assert result["code_quality"][0] == {"text": "dup null check", "severity": "Low", "effort": "Quick fix"}
    assert result["total_issues_found"] == 2


def test_testing_priority_tests_both_shapes():
    result = normalize_testing_strategy(
        {"priority_tests": ["plain test", {"text": "object test", "effort": "Easy"}], "missing_tests": []}
    )
    texts = [t["text"] for t in result["priority_tests"]]
    assert texts == ["plain test", "object test"]
    assert all("effort" in t for t in result["priority_tests"])


def test_blast_radius_enum_defaults():
    result = normalize_blast_radius({"impact_level": "catastrophic"})
    assert result["impact_level"] == "Medium"  # unknown value → safe default
    assert result["affected_modules"] == []


def test_confidence_report_drivers_and_clamping():
    result = normalize_confidence_report(
        {
            "score": 250,
            "score_drivers": {
                "blast_radius": [{"label": "x", "points": "-3.14159"}, "not a dict"],
                "engineering": None,
            },
        }
    )
    assert result["score"] == 100
    assert result["score_drivers"]["blast_radius"] == [{"label": "x", "points": -3.1}]
    assert result["score_drivers"]["engineering"] == []
    assert result["breakdown"]["blast_radius_max"] == 40


def test_history_risk_shape():
    result = normalize_history_risk(
        {"available": True, "window_commits": "12", "files": [{"path": "a.py", "fix_commits": "2"}, "junk"]}
    )
    assert result["available"] is True
    assert result["window_commits"] == 12
    assert result["files"] == [
        {"path": "a.py", "commits": 0, "fix_commits": 2, "last_modified_days": -1, "authors": 0}
    ]


def test_dependency_evidence_shape():
    result = normalize_dependency_evidence(
        {
            "available": True,
            "edges": [{"from_file": "b.py", "to_file": "a.py", "line": "7", "code": "import a"}, {"junk": 1}],
            "direct_dependents": "3",
        }
    )
    assert result["available"] is True
    assert result["direct_dependents"] == 3
    assert result["edges"] == [
        {"from_file": "b.py", "line": 7, "code": "import a", "to_file": "a.py", "symbol": ""}
    ]


def test_everything_survives_none():
    for fn in (
        normalize_change_analysis,
        normalize_blast_radius,
        normalize_engineering_review,
        normalize_testing_strategy,
        normalize_confidence_report,
        normalize_history_risk,
        normalize_dependency_evidence,
    ):
        assert isinstance(fn(None), dict)
