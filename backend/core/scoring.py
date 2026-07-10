"""
PRisk Scoring Engine
--------------------
The merge-confidence score is the product. This module makes it trustworthy:

  1. DETERMINISTIC — same inputs, same score. No LLM in the arithmetic.
  2. GRANULAR — continuous math over measured quantities (real diff lines,
     issue counts weighted by severity, downstream services, hotspot files),
     not four coarse buckets. Two different PRs virtually never tie.
  3. EVIDENCE-BLENDED — AI judgment (impact level, severity) sets the base,
     but hard facts (git history, test files in the diff, diff size) move it.
  4. EXPLAINABLE — every dimension returns "drivers": the exact signals and
     the points they cost or restored. Nothing about the score is a mystery.

Weights preserve the product's identity:
  Blast Radius 40 · Engineering 30 · Testing 20 · Complexity 10
"""

from typing import Any

from core.fallbacks import count_changed_lines, _is_test_file


# ── small helpers ─────────────────────────────────────────────────────────────

def _saturate(x: float, k: float) -> float:
    """Smooth 0→1 curve: fast growth early, diminishing returns later."""
    if x <= 0:
        return 0.0
    return x / (x + k)


def _clamp(x: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, x))


def _level(value: Any, default: str = "unknown") -> str:
    return str(value or default).strip().lower()


class _Drivers:
    """Collects (label, points) pairs; negative points = confidence lost."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, label: str, points: float) -> None:
        points = round(points, 1)
        if points != 0:
            self.items.append({"label": label, "points": points})


# ── Blast Radius (40 pts) ─────────────────────────────────────────────────────

_BLAST_BASE_PENALTY = {"low": 0.12, "none": 0.08, "medium": 0.42, "high": 0.68, "critical": 0.92, "unknown": 0.40}


def _score_blast(blast: dict, history: dict, changed_files: list[str]) -> tuple[int, list[dict]]:
    max_pts = 40.0
    drivers = _Drivers()

    level = _level(blast.get("impact_level"))
    base = _BLAST_BASE_PENALTY.get(level, 0.40)
    drivers.add(f"AI-assessed impact level: {level.title()}", -base * 0.55 * max_pts)

    downstream = max(0, int(blast.get("estimated_downstream_services") or 0))
    if downstream:
        frac = _saturate(downstream, 6) * 0.22
        drivers.add(f"{downstream} downstream service{'s' if downstream != 1 else ''} potentially affected", -frac * max_pts)
    else:
        frac = 0.0

    file_count = len(changed_files)
    breadth = min(max(0, file_count - 3) * 0.015, 0.08)
    if breadth:
        drivers.add(f"Change spans {file_count} files", -breadth * max_pts)

    hist_frac = 0.0
    if history.get("available"):
        hotspots = history.get("hotspots") or []
        fixes_total = sum(int(f.get("fix_commits") or 0) for f in history.get("files") or [])
        if hotspots:
            hist_frac = min(len(hotspots) * 0.13, 0.26)
            drivers.add(
                f"{len(hotspots)} hotspot file{'s' if len(hotspots) != 1 else ''} with repeated fix history touched",
                -hist_frac * max_pts,
            )
        elif fixes_total:
            hist_frac = 0.06
            drivers.add("Touched files have some fix history", -hist_frac * max_pts)
        else:
            drivers.add("Git history is clean for the touched files", +0.04 * max_pts)
            hist_frac = -0.04

    penalty = _clamp(base * 0.55 + frac + breadth + hist_frac)
    return round(max_pts * (1 - penalty)), drivers.items


# ── Engineering (30 pts) ──────────────────────────────────────────────────────

_SEVERITY_WEIGHT = {"critical": 1.0, "high": 0.55, "medium": 0.25, "low": 0.10}
_ENG_LEVEL_PENALTY = {"low": 0.05, "medium": 0.35, "high": 0.65, "critical": 0.90, "unknown": 0.35}


def _iter_findings(engineering: dict):
    """Yield (category, severity_weight) for every finding, string or object."""
    for category in ("security", "performance", "maintainability", "code_quality"):
        for item in engineering.get(category) or []:
            if isinstance(item, dict):
                severity = _level(item.get("severity"), "medium")
            else:
                severity = "high" if category == "security" else "medium"
            weight = _SEVERITY_WEIGHT.get(severity, 0.25)
            if category == "security":
                weight *= 1.5  # security findings hurt confidence more
            yield category, severity, weight


def _score_engineering(engineering: dict) -> tuple[int, list[dict]]:
    max_pts = 30.0
    drivers = _Drivers()

    load = 0.0
    counts: dict[str, int] = {}
    security_count = 0
    for category, severity, weight in _iter_findings(engineering):
        load += weight
        counts[severity] = counts.get(severity, 0) + 1
        if category == "security":
            security_count += 1

    finding_penalty = _saturate(load, 2.0)
    for severity in ("critical", "high", "medium", "low"):
        n = counts.get(severity, 0)
        if n:
            share = (_SEVERITY_WEIGHT[severity] * n) / load if load else 0
            suffix = " (security weighted 1.5×)" if security_count and severity in ("critical", "high") else ""
            drivers.add(
                f"{n} {severity}-severity finding{'s' if n != 1 else ''}{suffix}",
                -finding_penalty * share * 0.85 * max_pts,
            )

    level = _level(engineering.get("overall_severity"))
    level_penalty = _ENG_LEVEL_PENALTY.get(level, 0.35)
    drivers.add(f"AI overall severity: {level.title()}", -level_penalty * 0.15 * max_pts)

    penalty = _clamp(0.85 * finding_penalty + 0.15 * level_penalty)
    score = max_pts * (1 - penalty)

    positives = len(engineering.get("positive_notes") or [])
    if positives:
        credit = min(positives * 0.5, 1.5)
        drivers.add(f"{positives} positive note{'s' if positives != 1 else ''} from review", +credit)
        score += credit

    return round(_clamp(score, 0, max_pts)), drivers.items


# ── Testing (20 pts) ──────────────────────────────────────────────────────────

_TEST_BASE_PENALTY = {"likely adequate": 0.15, "needs more tests": 0.50, "critical gaps": 0.85, "unknown": 0.50}


def _score_testing(testing: dict, changed_files: list[str]) -> tuple[int, list[dict]]:
    max_pts = 20.0
    drivers = _Drivers()

    assessment = _level(testing.get("test_coverage_assessment"))
    base = _TEST_BASE_PENALTY.get(assessment, 0.50)
    drivers.add(f"AI coverage assessment: {assessment.title()}", -base * 0.70 * max_pts)

    # Hard fact: did this PR actually touch any test files?
    tests_changed = any(_is_test_file(path) for path in changed_files)
    if tests_changed:
        relief = -0.15
        drivers.add("PR includes test file changes", +0.15 * max_pts)
    else:
        relief = 0.10
        drivers.add("No test files modified in this PR", -0.10 * max_pts)

    missing = len(testing.get("missing_tests") or [])
    missing_frac = min(missing * 0.02, 0.12)
    if missing:
        drivers.add(f"{missing} missing test{'s' if missing != 1 else ''} identified", -missing_frac * max_pts)

    penalty = _clamp(base * 0.70 + relief + missing_frac)
    return round(max_pts * (1 - penalty)), drivers.items


# ── Complexity (10 pts) ───────────────────────────────────────────────────────

_COMPLEXITY_LEVEL_PENALTY = {"low": 0.10, "medium": 0.50, "high": 0.90, "unknown": 0.50}


def _score_complexity(change: dict, diff: str, changed_files: list[str]) -> tuple[int, list[dict]]:
    max_pts = 10.0
    drivers = _Drivers()

    # Hard fact: real changed-line count from the diff, not the LLM's estimate.
    lines = count_changed_lines(diff)
    line_frac = _saturate(lines, 350) * 0.55
    drivers.add(f"≈{lines} changed lines (measured from diff)", -line_frac * max_pts)

    files = len(changed_files)
    file_frac = _saturate(files, 10) * 0.25
    drivers.add(f"{files} file{'s' if files != 1 else ''} touched", -file_frac * max_pts)

    level = _level(change.get("complexity"))
    level_frac = _COMPLEXITY_LEVEL_PENALTY.get(level, 0.50) * 0.20
    drivers.add(f"AI-assessed complexity: {level.title()}", -level_frac * max_pts)

    penalty = _clamp(line_frac + file_frac + level_frac)
    return round(max_pts * (1 - penalty)), drivers.items


# ── Public API ────────────────────────────────────────────────────────────────

def compute_confidence(
    blast_radius: dict,
    engineering_review: dict,
    testing_strategy: dict,
    change_analysis: dict,
    history_risk: dict,
    changed_files: list[str],
    diff: str,
) -> dict:
    """
    Deterministic, evidence-blended confidence score with full provenance.
    Returns the same outer shape the frontend already binds to, plus
    `score_drivers` explaining every dimension.
    """
    blast_score, blast_drivers = _score_blast(blast_radius or {}, history_risk or {}, changed_files or [])
    eng_score, eng_drivers = _score_engineering(engineering_review or {})
    test_score, test_drivers = _score_testing(testing_strategy or {}, changed_files or [])
    complexity_score, complexity_drivers = _score_complexity(change_analysis or {}, diff or "", changed_files or [])

    total = int(blast_score + eng_score + test_score + complexity_score)

    if total >= 80:
        recommendation, color = "Safe to Merge", "green"
    elif total >= 60:
        recommendation, color = "Needs Validation", "amber"
    else:
        recommendation, color = "Do Not Merge", "red"

    return {
        "score": total,
        "recommendation": recommendation,
        "recommendation_color": color,
        "breakdown": {
            "blast_radius_score": blast_score,
            "blast_radius_max": 40,
            "engineering_score": eng_score,
            "engineering_max": 30,
            "testing_score": test_score,
            "testing_max": 20,
            "complexity_score": complexity_score,
            "complexity_max": 10,
        },
        "score_drivers": {
            "blast_radius": blast_drivers,
            "engineering": eng_drivers,
            "testing": test_drivers,
            "complexity": complexity_drivers,
        },
        "input_levels": {
            "blast_radius_level": _level(blast_radius.get("impact_level") if blast_radius else None),
            "engineering_severity": _level(engineering_review.get("overall_severity") if engineering_review else None),
            "testing_assessment": _level(testing_strategy.get("test_coverage_assessment") if testing_strategy else None),
            "complexity": _level(change_analysis.get("complexity") if change_analysis else None),
        },
    }
