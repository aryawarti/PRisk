"""Response payload assembly and the honesty label (analysis_quality)."""

from main import build_analysis_quality, build_response_payload


def _minimal_state():
    return {
        "pr_url": "https://github.com/a/b/pull/1",
        "repo_name": "a/b",
        "pr_title": "t",
        "pr_description": "",
        "author": "dev",
        "name": "t",
        "changed_files": ["x.py"],
        "history_risk": {"available": False},
        "dependency_evidence": {"available": False},
        "change_analysis": {"summary": "s", "complexity": "Low"},
        "blast_radius": {"impact_level": "Low"},
        "engineering_review": {"overall_severity": "Low"},
        "testing_strategy": {"test_coverage_assessment": "Likely Adequate"},
        "confidence_report": {"score": 90, "recommendation": "Safe to Merge", "recommendation_color": "green"},
        "errors": [],
    }


def test_payload_has_full_contract():
    payload = build_response_payload(_minimal_state())
    for key in (
        "success",
        "pr_url",
        "repo_name",
        "changed_files",
        "history_risk",
        "dependency_evidence",
        "analysis_quality",
        "change_analysis",
        "blast_radius",
        "engineering_review",
        "testing_strategy",
        "confidence_report",
        "errors",
    ):
        assert key in payload
    # Normalization guarantees nested shape even from minimal agent output
    assert "score_drivers" in payload["confidence_report"]
    assert "key_changes" in payload["change_analysis"]


def test_quality_full_when_clean():
    quality = build_analysis_quality([])
    assert quality["mode"] == "full"
    assert quality["degraded_agents"] == []


def test_quality_summary_fallback_stays_full_mode():
    quality = build_analysis_quality(["Agent 5 used summary fallback: boom"])
    assert quality["mode"] == "full"
    assert "Confidence Summary" in quality["degraded_agents"]


def test_quality_partial_when_clone_failed():
    quality = build_analysis_quality(["Repo clone/summary failed: network"])
    assert quality["mode"] == "partial"
    assert quality["history_evidence"] is False
