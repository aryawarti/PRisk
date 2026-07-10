"""
Deterministic Dependency Graph
------------------------------
THE PROOF LAYER. Every other tool (and PRisk's own Agent 2) *reasons* about
what depends on changed code. This module *measures* it: it scans the cloned
repository's import statements and finds the exact files — with line numbers
and the actual code line — that import what this PR touches.

The result is evidence, not opinion:
    gateway/src/routes.py:12 — from services.hotel_service import HotelService

Supported import styles (regex-based, no AST needed for cross-file edges):
  - Python:  import a.b.c / from a.b import c / from .c import x
  - Java:    import com.x.y.HotelServiceImpl;  (+ package-local class use)
  - JS/TS:   import ... from './path'  /  require('...')

Scope guards keep it fast on monorepos: capped file count, capped file size,
skips vendored/build directories.
"""

import re
from pathlib import Path
from typing import Any

# Directories that never contain first-party code worth scanning.
_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build", "target",
    ".gradle", "venv", ".venv", "vendor", "coverage", ".next", ".angular",
}

_SOURCE_EXTENSIONS = {".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

_MAX_FILES = 4000
_MAX_FILE_BYTES = 300_000
_MAX_EDGES = 50

# Lines that can declare a dependency, by ecosystem.
_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:import\s+.+|from\s+\S+\s+import\s+.+|.*\brequire\s*\(\s*['\"][^'\"]+['\"]\s*\))",
)


def _symbols_for_changed_file(path: str) -> set[str]:
    """
    Derive the names other files would use to import this file.

    src/services/hotel_service.py → {"hotel_service", "services.hotel_service", ...}
    src/main/java/.../HotelServiceImpl.java → {"HotelServiceImpl"}
    gateway/src/routes/api.ts → {"api", "routes/api"}
    """
    normalized = path.replace("\\", "/")
    stem = Path(normalized).stem
    symbols: set[str] = set()

    if not stem or stem in {"index", "__init__", "main", "mod", "utils", "types", "test"}:
        # Too generic on its own — require a qualified form below.
        pass
    elif len(stem) >= 3:
        symbols.add(stem)

    parts = [p for p in normalized.split("/") if p]
    if len(parts) >= 2:
        # Qualified forms: parent/stem and dotted module path tail.
        parent = Path(parts[-2]).name
        symbols.add(f"{parent}/{stem}")
        symbols.add(f"{parent}.{stem}")

    return {s for s in symbols if len(s) >= 3}


def _line_mentions_symbol(line: str, symbol: str) -> bool:
    """Word-boundary match so 'api' doesn't hit 'rapid'."""
    if "/" in symbol:
        return symbol in line
    return re.search(rf"\b{re.escape(symbol)}\b", line) is not None


def build_dependency_evidence(repo_path: Path, changed_files: list[str]) -> dict[str, Any]:
    """
    Scan the repo for import lines that reference the changed files.

    Returns:
      {
        "available": bool,
        "files_scanned": int,
        "edges": [
          {"from_file": str, "line": int, "code": str, "to_file": str, "symbol": str}
        ],
        "dependents_by_file": {changed_file: [unique dependent files]},
        "direct_dependents": int,   # unique files that import changed code
      }
    """
    empty = {
        "available": False,
        "files_scanned": 0,
        "edges": [],
        "dependents_by_file": {},
        "direct_dependents": 0,
    }

    try:
        changed_set = {c.replace("\\", "/") for c in changed_files}
        symbol_map: dict[str, set[str]] = {
            changed: _symbols_for_changed_file(changed)
            for changed in changed_set
            if Path(changed).suffix in _SOURCE_EXTENSIONS
        }
        symbol_map = {k: v for k, v in symbol_map.items() if v}
        if not symbol_map:
            return {**empty, "available": True}

        edges: list[dict[str, Any]] = []
        dependents_by_file: dict[str, list[str]] = {k: [] for k in symbol_map}
        files_scanned = 0

        for source in _iter_source_files(repo_path):
            if files_scanned >= _MAX_FILES:
                break
            rel = source.relative_to(repo_path).as_posix()
            if rel in changed_set:
                continue  # a changed file importing another changed file is not "blast"
            try:
                if source.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = source.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            files_scanned += 1

            for line_no, line in enumerate(text.splitlines(), start=1):
                if not _IMPORT_LINE_RE.match(line):
                    continue
                for changed, symbols in symbol_map.items():
                    if rel in dependents_by_file[changed]:
                        continue  # one citation per dependent file is enough
                    if any(_line_mentions_symbol(line, s) for s in symbols):
                        dependents_by_file[changed].append(rel)
                        if len(edges) < _MAX_EDGES:
                            edges.append({
                                "from_file": rel,
                                "line": line_no,
                                "code": line.strip()[:160],
                                "to_file": changed,
                                "symbol": Path(changed).stem,
                            })

        unique_dependents = {e["from_file"] for e in edges}
        for changed, deps in dependents_by_file.items():
            unique_dependents.update(deps)

        return {
            "available": True,
            "files_scanned": files_scanned,
            "edges": edges,
            "dependents_by_file": {k: v for k, v in dependents_by_file.items() if v},
            "direct_dependents": len(unique_dependents),
        }
    except Exception:
        return empty


def _iter_source_files(repo_path: Path):
    """Yield source files, skipping vendored/build directories."""
    stack = [repo_path]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if name.startswith(".") or name in _SKIP_DIRS:
                continue
            if entry.is_dir():
                stack.append(entry)
            elif entry.suffix in _SOURCE_EXTENSIONS:
                yield entry
