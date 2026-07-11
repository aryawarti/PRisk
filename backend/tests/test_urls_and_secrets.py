"""URL parsing and secret scrubbing — the security-critical string handling."""

import pytest

from core.context_builder import parse_pr_url, scrub_secrets


def test_parse_valid_url():
    assert parse_pr_url("https://github.com/octocat/Hello-World/pull/42") == ("octocat", "Hello-World", 42)


def test_parse_tolerates_trailing_paths():
    owner, repo, number = parse_pr_url("https://github.com/a/b/pull/7/files")
    assert (owner, repo, number) == ("a", "b", 7)


@pytest.mark.parametrize(
    "bad",
    [
        "https://gitlab.com/a/b/pull/1",
        "https://github.com/a/b/issues/1",
        "not a url",
        "https://github.com/a/b",
    ],
)
def test_parse_rejects_bad_urls(bad):
    with pytest.raises(ValueError):
        parse_pr_url(bad)


def test_scrub_removes_token_from_clone_urls(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_SECRET123")
    dirty = "clone failed: https://x-access-token:ghp_SECRET123@github.com/x/y and again ghp_SECRET123"
    cleaned = scrub_secrets(dirty)
    assert "ghp_SECRET123" not in cleaned
    assert "***" in cleaned


def test_scrub_handles_missing_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert scrub_secrets("plain error message") == "plain error message"
