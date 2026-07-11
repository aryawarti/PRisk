"""
Repository Context Builder
--------------------------
This is NOT an agent. It's a setup step that runs BEFORE the LangGraph workflow.

Responsibilities:
  1. Parse PR URL → extract owner/repo/PR number
  2. Use GitHub API to fetch PR metadata, diff, and changed files
  3. Clone the repository locally (using GitPython)
  4. Walk the directory tree to understand project structure
  5. Ask LLM to write a plain-English repository summary
  6. Return everything packed into the initial DiffVisionState

Why do this before LangGraph?
  Because all 3 parallel agents need this data simultaneously.
  Build it once, share it via state.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

import git
from github import Github, GithubException
from dotenv import load_dotenv

from core.llm import get_llm
from core.dependency_graph import build_dependency_evidence
from core.fallbacks import infer_repository_summary
from core.state import PRiskState

load_dotenv()

# Optional callback used by the streaming endpoint: emit(stage, label)
EmitFn = Callable[[str, str], None]

# Matches token-in-URL patterns like https://x-access-token:ghp_xxx@github.com/...
_AUTH_URL_RE = re.compile(r"(x-access-token:)[^@\s]+@")


def scrub_secrets(text: str) -> str:
    """
    Remove credentials from any string that might reach logs or API clients.
    GitPython errors, in particular, echo the full clone command including
    the token-authenticated URL.
    """
    cleaned = _AUTH_URL_RE.sub(r"\1***@", text)
    token = os.getenv("GITHUB_TOKEN")
    if token:
        cleaned = cleaned.replace(token, "***")
    return cleaned


# ── GitHub helpers ────────────────────────────────────────────────────────────

def parse_pr_url(url: str) -> tuple[str, str, int]:
    """
    "https://github.com/owner/repo/pull/42"
          → ("owner", "repo", 42)

    Raises ValueError if the URL doesn't match the expected pattern.
    """
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, url)
    if not match:
        raise ValueError(
            f"Invalid GitHub PR URL: {url}\n"
            "Expected format: https://github.com/owner/repo/pull/123"
        )
    owner, repo, pr_number = match.groups()
    return owner, repo, int(pr_number)


def fetch_pr_data(owner: str, repo: str, pr_number: int) -> dict:
    """
    Use PyGithub to download everything we need about the PR:
      - Title & description
      - The unified diff text
      - List of changed file paths
    """
    token = os.getenv("GITHUB_TOKEN")
    gh = Github(token) if token else Github()

    try:
        repository = gh.get_repo(f"{owner}/{repo}")
        pull = repository.get_pull(pr_number)
    except GithubException as e:
        error_data = getattr(e, "data", {})
        message = error_data.get("message", str(e)) if isinstance(error_data, dict) else str(e)
        if e.status == 404:
            message = (
                f"Pull request not found: {owner}/{repo} #{pr_number}. "
                "Check that the repository name and PR number are correct, "
                "and that the repository is accessible."
            )
        elif not token and e.status == 403:
            message = (
                "GitHub rate limit reached for unauthenticated requests. "
                "Set GITHUB_TOKEN in backend/.env and try again."
            )
        raise RuntimeError(f"GitHub API error: {message}")

    diff_lines = []
    changed_files = []

    for file in pull.get_files():
        changed_files.append(file.filename)
        if file.patch:                      # some files (binary) have no patch
            diff_lines.append(f"--- a/{file.filename}") 
            diff_lines.append(f"+++ b/{file.filename}")
            diff_lines.append(file.patch)
            diff_lines.append("")           # blank separator between files

    author = pull.user.login if pull.user else ""
 
    return {
        "title": pull.title,
        "description": pull.body or "",
        "author": author,
        "name": pull.title,
        "diff": "\n".join(diff_lines),
        "changed_files": changed_files,
        "base_sha": pull.base.sha,
        "head_sha": pull.head.sha,
        "clone_url": repository.clone_url,
    }


# ── Repository cloning & structure analysis ───────────────────────────────────

def clone_repo(clone_url: str, token: str) -> Path:
    """
    Clone the repo into a temp directory and return the path.
    Uses token auth so private repos work too.
    """
    clone_dir = Path(os.getenv("REPO_CLONE_DIR", Path(tempfile.gettempdir()) / "prisk_repos"))
    clone_dir.mkdir(parents=True, exist_ok=True)

    auth_url = clone_url
    if token and clone_url.startswith("https://"):
        encoded_token = quote(token, safe="")
        auth_url = clone_url.replace("https://", f"https://x-access-token:{encoded_token}@", 1)

    # Create a unique subfolder so parallel runs don't collide
    import hashlib
    import time

    folder = clone_dir / hashlib.md5(
        (clone_url + str(time.time())).encode()
    ).hexdigest()[:8]

    # Shallow-but-not-single-commit clone: we need recent history for the
    # historical risk evidence (hotfix/churn mining). 300 commits is enough
    # signal for a 90-day window on most repos while staying fast.
    depth = int(os.getenv("CLONE_DEPTH", "300"))
    git.Repo.clone_from(auth_url, folder, depth=depth, single_branch=True)
    return folder


def read_directory_structure(repo_path: Path, max_depth: int = 3) -> str:
    """
    Walk the repo tree and return a human-readable directory listing.
    We cap depth so massive monorepos don't overwhelm the LLM prompt.

    Output looks like:
        src/
          main/
            java/
              UserService.java
              OrderService.java
          test/
            ...
    """
    lines = []

    def walk(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir())
        except PermissionError:
            return

        for entry in entries:
            # Skip hidden files/dirs and common noise
            if entry.name.startswith("."):
                continue
            if entry.name in {"node_modules", "__pycache__", ".git",
                               "dist", "build", "target", ".gradle"}:
                continue

            indent = "  " * depth
            if entry.is_dir():
                lines.append(f"{indent}{entry.name}/")
                walk(entry, depth + 1)
            else:
                lines.append(f"{indent}{entry.name}")

    walk(repo_path, 0)
    return "\n".join(lines[:200])          # cap at 200 lines


# ── Historical risk mining ────────────────────────────────────────────────────

# Commit messages that indicate a defect was being repaired.
_FIX_PATTERN = re.compile(r"\b(fix(es|ed)?|hotfix|revert(s|ed)?|bug|patch(es|ed)?|regression)\b", re.IGNORECASE)


def mine_history_risk(repo_path: Path, changed_files: list[str], max_commits: int = 300) -> dict:
    """
    Evidence-based risk: walk recent commit history and, for every file this
    PR touches, count how often it changed and how often those changes were
    fixes/reverts/hotfixes. A file that keeps needing fixes is empirically
    risky to change — no LLM opinion required.

    Note: history comes from the default branch of the clone, which is the
    right baseline ("how has this file behaved in mainline so far").

    Returns a dict:
      {
        "available": bool,
        "window_commits": int,
        "overall_level": "Low" | "Medium" | "High",
        "hotspots": ["path", ...],           # files with repeated fix history
        "files": [
          {"path", "commits", "fix_commits", "last_modified_days", "authors"}
        ],
      }
    """
    try:
        repo = git.Repo(repo_path)
        raw = repo.git.log(
            f"-{max_commits}",
            "--name-only",
            "--no-merges",
            "--pretty=format:__COMMIT__%ct|%an|%s",
        )
    except Exception:
        return {"available": False, "window_commits": 0, "overall_level": "Low", "hotspots": [], "files": []}

    changed = set(changed_files)
    stats: dict[str, dict] = {
        path: {"commits": 0, "fix_commits": 0, "last_ts": 0, "authors": set()}
        for path in changed
    }

    import time as _time

    commit_count = 0
    is_fix = False
    author = ""
    timestamp = 0

    for line in raw.splitlines():
        if line.startswith("__COMMIT__"):
            commit_count += 1
            try:
                ts_str, author, subject = line[len("__COMMIT__"):].split("|", 2)
                timestamp = int(ts_str)
            except ValueError:
                timestamp, author, subject = 0, "", ""
            is_fix = bool(_FIX_PATTERN.search(subject))
        elif line.strip() and line.strip() in changed:
            entry = stats[line.strip()]
            entry["commits"] += 1
            if is_fix:
                entry["fix_commits"] += 1
            if author:
                entry["authors"].add(author)
            entry["last_ts"] = max(entry["last_ts"], timestamp)

    now = _time.time()
    files = []
    for path, entry in stats.items():
        if entry["commits"] == 0:
            continue  # new file or renamed — no history to report
        files.append({
            "path": path,
            "commits": entry["commits"],
            "fix_commits": entry["fix_commits"],
            "last_modified_days": max(0, int((now - entry["last_ts"]) / 86400)) if entry["last_ts"] else -1,
            "authors": len(entry["authors"]),
        })

    files.sort(key=lambda f: (f["fix_commits"], f["commits"]), reverse=True)
    hotspots = [f["path"] for f in files if f["fix_commits"] >= 2]

    if hotspots:
        overall = "High"
    elif any(f["fix_commits"] >= 1 for f in files):
        overall = "Medium"
    else:
        overall = "Low"

    return {
        "available": True,
        "window_commits": commit_count,
        "overall_level": overall,
        "hotspots": hotspots,
        "files": files[:20],
    }


def summarise_repository(structure: str, changed_files: list[str]) -> str:
    """
    Ask the LLM to write a 2-3 sentence summary of what this repo is,
    which modules it has, and what tech stack it uses.

    This summary is shared with all agents in the state.
    """
    prompt = f"""You are analysing a software repository for a code review tool.

Repository directory structure:
{structure}

Files changed in this PR:
{chr(10).join(changed_files)}

Write a concise 2-3 sentence summary that covers:
1. What kind of application this is (e.g., "Spring Boot REST API")
2. The main modules/packages it contains
3. The tech stack

Keep it factual. Do not pad. Output ONLY the summary text, nothing else."""

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception:
        return infer_repository_summary(structure, changed_files)


# ── Public entry point ────────────────────────────────────────────────────────

def build_repository_context(
    pr_url: str,
    emit: Optional[EmitFn] = None,
    pr_data: Optional[dict] = None,
) -> PRiskState:
    """
    Main function called by the FastAPI endpoint.
    Returns a fully populated initial PRiskState ready for LangGraph.

    `emit(stage, label)` is an optional callback used by the streaming
    endpoint to surface real-time progress to the frontend.

    Steps:
      1. Parse URL
      2. Fetch PR from GitHub
      3. Clone repo
      4. Read structure
      5. Generate summary
      6. Clean up temp clone
      7. Return initial state
    """
    def notify(stage: str, label: str) -> None:
        if emit:
            emit(stage, label)

    errors: list[str] = []
    repo_path: Optional[Path] = None

    # Step 1: Parse URL (status only emitted if the endpoint didn't already)
    if pr_data is None:
        notify("parse", "Validating pull request link…")
    owner, repo_slug, pr_number = parse_pr_url(pr_url)
    repo_name = f"{owner}/{repo_slug}"

    # Step 2: Fetch PR data from GitHub (skipped when the endpoint already
    # fetched it for the per-commit cache check — no duplicate API call).
    if pr_data is None:
        notify("fetch", f"Fetching PR #{pr_number} from {repo_name}…")
        pr_data = fetch_pr_data(owner, repo_slug, pr_number)
    file_count = len(pr_data["changed_files"])
    notify("diff", f"Reading diff — {file_count} changed file{'s' if file_count != 1 else ''}…")

    # Step 3 & 4: Clone + read structure + mine history
    repo_summary = ""
    history_risk = {"available": False, "window_commits": 0, "overall_level": "Low", "hotspots": [], "files": []}
    dependency_evidence = {"available": False, "files_scanned": 0, "edges": [], "dependents_by_file": {}, "direct_dependents": 0}
    try:
        token = os.getenv("GITHUB_TOKEN", "")
        notify("clone", "Cloning repository for structural context…")
        repo_path = clone_repo(pr_data["clone_url"], token)
        structure = read_directory_structure(repo_path)
        notify("history", "Mining commit history for risk evidence…")
        history_risk = mine_history_risk(repo_path, pr_data["changed_files"])
        notify("graph", "Mapping the import graph — measuring real dependents…")
        dependency_evidence = build_dependency_evidence(repo_path, pr_data["changed_files"])
        notify("summary", "Summarising the codebase…")
        repo_summary = summarise_repository(structure, pr_data["changed_files"])
    except Exception as e:
        errors.append(f"Repo clone/summary failed: {scrub_secrets(str(e))}")
        repo_summary = (
            "Repository structure could not be cloned locally; analysis will continue "
            "with GitHub metadata only."
        )
    finally:
        # Step 6: Remove temp clone to free disk space
        if repo_path and repo_path.exists():
            shutil.rmtree(repo_path, ignore_errors=True)

    # Step 7: Pack into initial state
    return PRiskState(
        pr_url=pr_url,
        repo_name=repo_name,
        diff=pr_data["diff"],
        changed_files=pr_data["changed_files"],
        repo_summary=repo_summary,
        history_risk=history_risk,
        dependency_evidence=dependency_evidence,
        pr_title=pr_data["title"],
        pr_description=pr_data["description"],
        author=pr_data["author"],
        name=pr_data["name"],
        change_analysis={},
        blast_radius={},
        engineering_review={},
        testing_strategy={},
        confidence_report={},
        errors=errors,
    )
