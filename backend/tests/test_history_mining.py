"""History mining: hotfix evidence must come from real commits."""

import shutil
import subprocess

import pytest

from core.context_builder import mine_history_risk

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")


def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.email=t@t.t", "-c", "user.name=t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@requires_git
def test_counts_fix_commits_and_flags_hotspots(tmp_path):
    _git(tmp_path, "init", "-q")
    target = tmp_path / "fragile.py"

    target.write_text("v1")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "add fragile module")

    target.write_text("v2")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "fix crash in fragile module")

    target.write_text("v3")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "hotfix regression in fragile module")

    (tmp_path / "stable.py").write_text("ok")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "add stable module")

    result = mine_history_risk(tmp_path, ["fragile.py", "stable.py", "brand_new.py"])

    assert result["available"] is True
    assert result["window_commits"] == 4
    assert "fragile.py" in result["hotspots"]
    assert result["overall_level"] == "High"

    by_path = {f["path"]: f for f in result["files"]}
    assert by_path["fragile.py"]["fix_commits"] == 2
    assert by_path["fragile.py"]["commits"] == 3
    assert by_path["stable.py"]["fix_commits"] == 0
    assert "brand_new.py" not in by_path  # no history → not reported


@requires_git
def test_no_repo_fails_soft(tmp_path):
    result = mine_history_risk(tmp_path / "not-a-repo", ["a.py"])
    assert result["available"] is False
