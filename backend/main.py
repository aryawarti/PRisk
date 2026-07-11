"""
PRisk FastAPI Application
-------------------------
Exposes three endpoints:

  POST /api/analyse
    - Accepts a GitHub PR URL
    - Runs the full LangGraph pipeline
    - Returns the complete analysis report as JSON (invoke-and-wait)

  POST /api/analyse/stream
    - Same pipeline, but streams real-time status events over SSE
      while the analysis runs, ending with the full report.

  GET /health
    - Simple liveness probe (used by Render)

How a streaming request flows:
  Browser → POST /api/analyse/stream
         → worker thread: context_builder + LangGraph workflow
         → each stage pushes a status event onto a queue
         → async generator drains the queue → SSE frames → Angular UI
"""

import asyncio
import json
import os
import queue
import re
import threading
import time
import traceback
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.context_builder import build_repository_context, fetch_pr_data, parse_pr_url, scrub_secrets
from core.llm import AnalysisUnavailable, describe_llm_failure
from core.normalize import (
    normalize_blast_radius,
    normalize_change_analysis,
    normalize_confidence_report,
    normalize_dependency_evidence,
    normalize_engineering_review,
    normalize_history_risk,
    normalize_testing_strategy,
)
from core.workflow import run_analysis, stream_analysis

app = FastAPI(
    title="PRisk API",
    description="AI-Powered Pull Request Risk Intelligence Platform",
    version="1.1.0",
)

# CORS: local Angular dev server + deployed Vercel frontend.
# Extra origins (e.g. Vercel preview URLs) can be added via ALLOWED_ORIGINS
# as a comma-separated list — no redeploy-with-code-change needed.
_default_origins = [
    "http://localhost:4200",
    "https://p-risk.vercel.app",
]
_extra_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Abuse protection: per-IP sliding-window rate limit ──────────────────────
# In-memory — right-sized for a single Render instance. An analysis costs
# real LLM tokens and ~60s of compute; an open endpoint needs a ceiling.

RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "600"))
_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}


def enforce_rate_limit(http_request: Request) -> None:
    ip = http_request.client.host if http_request.client else "unknown"
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(ip, []) if now - t < RATE_LIMIT_WINDOW]
        if len(hits) >= RATE_LIMIT_MAX:
            retry_seconds = max(1, int(RATE_LIMIT_WINDOW - (now - hits[0])))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit reached: {RATE_LIMIT_MAX} analyses per "
                    f"{RATE_LIMIT_WINDOW // 60} minutes. Try again in about "
                    f"{max(1, retry_seconds // 60)} minute(s)."
                ),
            )
        hits.append(now)
        _rate_hits[ip] = hits


# ── Per-commit result cache ──────────────────────────────────────────────────
# Same PR + same head commit ⇒ same deterministic report. Re-analysing an
# unchanged PR should cost zero LLM calls and return instantly. A new push
# changes head_sha and naturally misses the cache.

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
_CACHE_MAX_ENTRIES = 100
_cache_lock = threading.Lock()
_result_cache: "OrderedDict[str, dict]" = OrderedDict()


def cache_get(key: str, head_sha: str) -> dict | None:
    with _cache_lock:
        entry = _result_cache.get(key)
        if not entry:
            return None
        if entry["head_sha"] != head_sha or time.time() - entry["time"] > CACHE_TTL_SECONDS:
            _result_cache.pop(key, None)
            return None
        _result_cache.move_to_end(key)
        return entry["payload"]


def cache_put(key: str, head_sha: str, payload: dict) -> None:
    with _cache_lock:
        _result_cache[key] = {"head_sha": head_sha, "time": time.time(), "payload": payload}
        _result_cache.move_to_end(key)
        while len(_result_cache) > _CACHE_MAX_ENTRIES:
            _result_cache.popitem(last=False)


# ── Request / Response models ────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    """What the frontend sends us."""
    pr_url: str = Field(..., min_length=1, max_length=500)


class AnalyseResponse(BaseModel):
    """What we send back to the frontend."""
    success: bool
    pr_url: str
    pr_title: str
    pr_description: str
    author: str
    name: str
    repo_name: str
    changed_files: list
    history_risk: dict
    dependency_evidence: dict
    analysis_quality: dict
    change_analysis: dict
    blast_radius: dict
    engineering_review: dict
    testing_strategy: dict
    confidence_report: dict
    errors: list


_AGENT_NAMES = {
    1: "Change Understanding",
    2: "Blast Radius",
    3: "Engineering Review",
    4: "Testing Strategy",
    5: "Confidence Summary",
}

_FALLBACK_RE = re.compile(r"Agent (\d) used (?:heuristic|summary) fallback")


def build_analysis_quality(errors: list) -> dict:
    """
    Honest label for how this report was produced. Users deciding whether to
    merge deserve to know if the AI actually ran or heuristics filled in.
    """
    degraded_ids = sorted({int(m.group(1)) for e in errors for m in [_FALLBACK_RE.search(str(e))] if m})
    clone_failed = any("clone/summary failed" in str(e).lower() for e in errors)

    # Agent 5's summary fallback doesn't affect the score, only prose.
    scoring_agents_degraded = [i for i in degraded_ids if i != 5]

    # Agents 1-4 abort the whole analysis on AI failure (strict mode), so a
    # produced report always has real AI analysis. Only two soft cases remain:
    # agent 5's summary prose fallback (score unaffected) and clone failure.
    if not scoring_agents_degraded and not clone_failed:
        mode = "full"
        note = (
            "Score computed deterministically; the executive summary used a deterministic fallback."
            if 5 in degraded_ids
            else "All five agents completed AI analysis with repository evidence."
        )
    else:
        mode = "partial"
        note = "Repository clone failed — history evidence unavailable; analysis used GitHub metadata only."

    return {
        "mode": mode,
        "degraded_agents": [_AGENT_NAMES[i] for i in degraded_ids],
        "history_evidence": not clone_failed,
        "note": note,
    }


def build_response_payload(final_state: dict) -> dict:
    """
    Serialize the final LangGraph state into the API response shape.
    Every agent output is normalized so the frontend can bind to it
    without null/shape guards, even when an LLM returned partial JSON.
    """
    return {
        "success": True,
        "pr_url": final_state["pr_url"],
        "pr_title": final_state.get("pr_title", ""),
        "pr_description": final_state.get("pr_description", ""),
        "author": final_state.get("author", ""),
        "name": final_state.get("name", ""),
        "repo_name": final_state["repo_name"],
        "changed_files": [str(f) for f in final_state.get("changed_files", [])],
        "history_risk": normalize_history_risk(final_state.get("history_risk")),
        "dependency_evidence": normalize_dependency_evidence(final_state.get("dependency_evidence")),
        "analysis_quality": build_analysis_quality(final_state.get("errors", [])),
        "change_analysis": normalize_change_analysis(final_state.get("change_analysis")),
        "blast_radius": normalize_blast_radius(final_state.get("blast_radius")),
        "engineering_review": normalize_engineering_review(final_state.get("engineering_review")),
        "testing_strategy": normalize_testing_strategy(final_state.get("testing_strategy")),
        "confidence_report": normalize_confidence_report(final_state.get("confidence_report")),
        "errors": [scrub_secrets(str(e)) for e in final_state.get("errors", [])],
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "PRisk API"}


@app.post("/api/analyse", response_model=AnalyseResponse)
def analyse_pr(request: AnalyseRequest, http_request: Request):
    """
    Invoke-and-wait endpoint (kept for compatibility / as streaming fallback).

    Deliberately a sync `def`: FastAPI runs it in a worker thread, so the
    long-running GitHub + LLM pipeline never blocks the event loop.
    """
    enforce_rate_limit(http_request)
    try:
        print(f"[PRisk] Starting analysis for: {request.pr_url}")
        owner, repo_slug, pr_number = parse_pr_url(request.pr_url)
        pr_data = fetch_pr_data(owner, repo_slug, pr_number)

        cache_key = f"{owner}/{repo_slug}#{pr_number}"
        cached = cache_get(cache_key, pr_data["head_sha"])
        if cached:
            print(f"[PRisk] Cache hit for {cache_key} @ {pr_data['head_sha'][:8]}")
            return AnalyseResponse(**cached)

        initial_state = build_repository_context(request.pr_url, pr_data=pr_data)
        print(f"[PRisk] Context built for: {initial_state['repo_name']}")

        print("[PRisk] Running LangGraph workflow...")
        final_state = run_analysis(initial_state)
        print(f"[PRisk] Analysis complete. Score: {final_state['confidence_report'].get('score', 'N/A')}")

        payload = build_response_payload(final_state)
        cache_put(cache_key, pr_data["head_sha"], payload)
        return AnalyseResponse(**payload)

    except ValueError as e:
        # Invalid URL format
        raise HTTPException(status_code=400, detail=scrub_secrets(str(e)))

    except AnalysisUnavailable as e:
        # AI provider failed — abort honestly rather than show heuristic guesses.
        raise HTTPException(
            status_code=503,
            detail=(
                f"AI analysis unavailable: {describe_llm_failure(str(e))}. "
                "No report was generated — PRisk never shows guessed results."
            ),
        )

    except RuntimeError as e:
        # GitHub API error (bad token, repo not found, rate limit, etc.)
        raise HTTPException(status_code=422, detail=scrub_secrets(str(e)))

    except Exception:
        # Unexpected error — log full details server-side, return a generic
        # message so internals (paths, tokens, stack frames) never leak.
        print(f"[PRisk] Unexpected error: {scrub_secrets(traceback.format_exc())}")
        raise HTTPException(
            status_code=500,
            detail="Unexpected error while analysing this pull request. Please try again.",
        )


@app.post("/api/analyse/stream")
def analyse_pr_stream(request: AnalyseRequest, http_request: Request):
    """
    Streaming endpoint. Emits Server-Sent Events while the pipeline runs:

      data: {"type": "status", "stage": "fetch", "label": "Fetching PR #42…"}
      data: {"type": "status", "stage": "blast_node", "label": "Blast radius mapped"}
      ...
      data: {"type": "result", "payload": { ...full report... }}

    or, on failure:

      data: {"type": "error", "status": 422, "message": "..."}

    The pipeline runs in a daemon thread; events flow through a queue to
    the async generator so the event loop stays free.
    """
    enforce_rate_limit(http_request)

    events: queue.Queue = queue.Queue()
    _SENTINEL = object()

    def emit(stage: str, label: str) -> None:
        events.put({"type": "status", "stage": stage, "label": label})

    def worker() -> None:
        try:
            print(f"[PRisk] (stream) Starting analysis for: {request.pr_url}")
            emit("parse", "Validating pull request link…")
            owner, repo_slug, pr_number = parse_pr_url(request.pr_url)
            emit("fetch", f"Fetching PR #{pr_number} from {owner}/{repo_slug}…")
            pr_data = fetch_pr_data(owner, repo_slug, pr_number)

            cache_key = f"{owner}/{repo_slug}#{pr_number}"
            cached = cache_get(cache_key, pr_data["head_sha"])
            if cached:
                emit("cache", "This commit was already analysed — returning the saved report…")
                events.put({"type": "result", "payload": cached})
                return

            initial_state = build_repository_context(request.pr_url, emit=emit, pr_data=pr_data)
            emit("agents", "Running risk agents — change, blast radius, engineering…")
            final_state = stream_analysis(initial_state, emit=emit)
            emit("finalize", "Preparing report…")
            payload = build_response_payload(final_state)
            cache_put(cache_key, pr_data["head_sha"], payload)
            events.put({"type": "result", "payload": payload})
        except ValueError as e:
            events.put({"type": "error", "status": 400, "message": scrub_secrets(str(e))})
        except AnalysisUnavailable as e:
            events.put({
                "type": "error",
                "status": 503,
                "message": (
                    f"AI analysis unavailable: {describe_llm_failure(str(e))}. "
                    "No report was generated — PRisk never shows guessed results."
                ),
            })
        except RuntimeError as e:
            events.put({"type": "error", "status": 422, "message": scrub_secrets(str(e))})
        except Exception:
            print(f"[PRisk] (stream) Unexpected error: {scrub_secrets(traceback.format_exc())}")
            events.put({
                "type": "error",
                "status": 500,
                "message": "Unexpected error while analysing this pull request. Please try again.",
            })
        finally:
            events.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    def _next_event():
        """Blocking queue read with a timeout so we can heartbeat."""
        try:
            return events.get(timeout=15)
        except queue.Empty:
            return None  # → heartbeat

    async def event_source():
        while True:
            item = await asyncio.to_thread(_next_event)
            if item is _SENTINEL:
                break
            if item is None:
                # SSE comment frame: keeps proxies from closing an idle
                # connection during long LLM calls. Ignored by clients.
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx-style)
        },
    )


# ── Dev server entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,       # Auto-restart on file changes during development
    )
