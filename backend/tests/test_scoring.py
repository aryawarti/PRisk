"""
Scoring engine tests — the trust-critical core.
Property-based assertions: determinism, bounds, monotonicity, provenance.
"""

from core.scoring import compute_confidence


def _inputs(
    impact="Medium",
    severity="Low",
    coverage="Needs More Tests",
    complexity="Low",
    files=None,
    diff="+ line\n- line\n",
    history=None,
    graph=None,
):
    return dict(
        blast_radius={"impact_level": impact, "estimated_downstream_services": 2},
        engineering_review={
            "security": [],
            "performance": [],
            "maintainability": [],
            "code_quality": [],
            "overall_severity": severity,
            "positive_notes": [],
        },
        testing_strategy={"test_coverage_assessment": coverage, "missing_tests": [], "priority_tests": []},
        change_analysis={"complexity": complexity},
        history_risk=history or {"available": False},
        changed_files=files or ["src/a.py"],
        diff=diff,
        dependency_evidence=graph,
    )


def test_deterministic_same_input_same_score():
    a = compute_confidence(**_inputs())
    b = compute_confidence(**_inputs())
    assert a["score"] == b["score"]
    assert a["breakdown"] == b["breakdown"]
    assert a["score_drivers"] == b["score_drivers"]


def test_score_bounds_and_breakdown_consistency():
    result = compute_confidence(**_inputs())
    assert 0 <= result["score"] <= 100
    bd = result["breakdown"]
    assert result["score"] == (
        bd["blast_radius_score"] + bd["engineering_score"] + bd["testing_score"] + bd["complexity_score"]
    )
    assert 0 <= bd["blast_radius_score"] <= 40
    assert 0 <= bd["engineering_score"] <= 30
    assert 0 <= bd["testing_score"] <= 20
    assert 0 <= bd["complexity_score"] <= 10


def test_worse_impact_scores_lower():
    low = compute_confidence(**_inputs(impact="Low"))
    critical = compute_confidence(**_inputs(impact="Critical"))
    assert critical["breakdown"]["blast_radius_score"] < low["breakdown"]["blast_radius_score"]


def test_security_findings_hurt_engineering():
    clean = compute_confidence(**_inputs())
    dirty_inputs = _inputs()
    dirty_inputs["engineering_review"]["security"] = [
        {"text": "SQL injection", "severity": "Critical", "effort": "Quick fix"}
    ]
    dirty = compute_confidence(**dirty_inputs)
    assert dirty["breakdown"]["engineering_score"] < clean["breakdown"]["engineering_score"]


def test_string_findings_are_tolerated():
    inputs = _inputs()
    inputs["engineering_review"]["code_quality"] = ["plain string finding"]
    result = compute_confidence(**inputs)
    assert 0 <= result["score"] <= 100


def test_measured_zero_dependents_beats_measured_many():
    none_graph = {"available": True, "direct_dependents": 0, "edges": [], "files_scanned": 50}
    many_graph = {"available": True, "direct_dependents": 8, "edges": [], "files_scanned": 50}
    safe = compute_confidence(**_inputs(graph=none_graph))
    risky = compute_confidence(**_inputs(graph=many_graph))
    assert safe["breakdown"]["blast_radius_score"] > risky["breakdown"]["blast_radius_score"]


def test_hotspot_history_lowers_blast_score():
    clean_history = {"available": True, "hotspots": [], "files": [{"path": "a.py", "fix_commits": 0}]}
    hot_history = {"available": True, "hotspots": ["a.py"], "files": [{"path": "a.py", "fix_commits": 3}]}
    clean = compute_confidence(**_inputs(history=clean_history))
    hot = compute_confidence(**_inputs(history=hot_history))
    assert hot["breakdown"]["blast_radius_score"] < clean["breakdown"]["blast_radius_score"]


def test_tests_in_diff_help_testing_score():
    without = compute_confidence(**_inputs(files=["src/a.py"]))
    with_tests = compute_confidence(**_inputs(files=["src/a.py", "tests/test_a.py"]))
    assert with_tests["breakdown"]["testing_score"] > without["breakdown"]["testing_score"]


def test_bigger_diff_lowers_complexity_score():
    small = compute_confidence(**_inputs(diff="+ a\n"))
    big = compute_confidence(**_inputs(diff="\n".join("+ line %d" % i for i in range(500))))
    assert big["breakdown"]["complexity_score"] < small["breakdown"]["complexity_score"]


def test_every_dimension_has_drivers():
    result = compute_confidence(**_inputs())
    drivers = result["score_drivers"]
    for key in ("blast_radius", "engineering", "testing", "complexity"):
        assert key in drivers
        for driver in drivers[key]:
            assert driver["label"]
            assert isinstance(driver["points"], (int, float))


def test_recommendation_bands():
    assert compute_confidence(**_inputs(impact="Low", severity="Low", coverage="Likely Adequate"))["score"] >= 80
    critical = compute_confidence(
        **_inputs(impact="Critical", severity="Critical", coverage="Critical Gaps", complexity="High")
    )
    assert critical["score"] < 60
    assert critical["recommendation"] == "Do Not Merge"
