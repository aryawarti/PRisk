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
        if not token and e.status == 403:
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

    git.Repo.clone_from(auth_url, folder, depth=1)  # depth=1 = fast shallow clone
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

def build_repository_context(pr_url: str, emit: Optional[EmitFn] = None) -> PRiskState:
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

    # Step 1: Parse URL
    notify("parse", "Validating pull request link…")
    owner, repo_slug, pr_number = parse_pr_url(pr_url)
    repo_name = f"{owner}/{repo_slug}"

    # Step 2: Fetch PR data from GitHub
    notify("fetch", f"Fetching PR #{pr_number} from {repo_name}…")
    pr_data = fetch_pr_data(owner, repo_slug, pr_number)
    file_count = len(pr_data["changed_files"])
    notify("diff", f"Reading diff — {file_count} changed file{'s' if file_count != 1 else ''}…")

    # Step 3 & 4: Clone + read structure
    repo_summary = ""
    try:
        token = os.getenv("GITHUB_TOKEN", "")
        notify("clone", "Cloning repository for structural context…")
        repo_path = clone_repo(pr_data["clone_url"], token)
        structure = read_directory_structure(repo_path)
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
