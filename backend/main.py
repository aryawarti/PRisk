"""
DiffVision FastAPI Application
--------------------------------
Exposes two endpoints:

  POST /api/analyse
    - Accepts a GitHub PR URL
    - Runs the full LangGraph pipeline
    - Returns the complete analysis report as JSON

  GET /health
    - Simple liveness probe (useful for deployment)

How a request flows:
  Browser → POST /api/analyse
         → context_builder (GitHub API + clone + summarise)
         → LangGraph workflow (5 agents)
         → JSON response → Angular frontend
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import traceback

from core.context_builder import build_repository_context
from core.workflow import run_analysis



app = FastAPI(
    title="PRisk API",
    description="AI-Powered Pull Request Risk Intelligence Platform",
    version="1.0.0",
)

# CORS: Allow the Angular frontend (running on localhost:4200) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",     # Angular dev server
        "https://p-risk.vercel.app",    # In case you use a different port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    """What the frontend sends us."""
    pr_url: str                         # e.g. "https://github.com/owner/repo/pull/42"


class AnalyseResponse(BaseModel):
    """What we send back to the frontend."""
    success: bool
    pr_url: str
    pr_title: str
    pr_description: str
    author: str
    name: str
    repo_name: str
    change_analysis: dict
    blast_radius: dict
    engineering_review: dict
    testing_strategy: dict
    confidence_report: dict
    errors: list


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "PRisk API"}


@app.post("/api/analyse", response_model=AnalyseResponse)
async def analyse_pr(request: AnalyseRequest):
    """
    Main endpoint. Full pipeline:
      1. Validate URL format
      2. Build repository context (GitHub API + clone)
      3. Run LangGraph workflow (5 agents)
      4. Return structured report
    """
    try:
        # Step 1: Build initial state from GitHub
        # This fetches the PR, clones the repo, and generates a summary
        print(f"[PRisk] Starting analysis for: {request.pr_url}")
        initial_state = build_repository_context(request.pr_url)
        print(f"[PRisk] Context built for: {initial_state['repo_name']}")

        # Step 2: Run the 5-agent LangGraph pipeline
        print("[PRisk] Running LangGraph workflow...")
        final_state = run_analysis(initial_state)
        print(f"[PRisk] Analysis complete. Score: {final_state['confidence_report'].get('score', 'N/A')}")

        # Step 3: Return the full report
        return AnalyseResponse(
            success=True,
            pr_url=final_state["pr_url"],
            pr_title=final_state.get("pr_title", ""),
            pr_description=final_state.get("pr_description", ""),
            author=final_state.get("author", ""),
            name=final_state.get("name", ""),
            repo_name=final_state["repo_name"],
            change_analysis=final_state["change_analysis"],
            blast_radius=final_state["blast_radius"],
            engineering_review=final_state["engineering_review"],
            testing_strategy=final_state["testing_strategy"],
            confidence_report=final_state["confidence_report"],
            errors=final_state.get("errors", []),
        )

    except ValueError as e:
        # Invalid URL format
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        # GitHub API error (bad token, repo not found, etc.)
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected error — log it but don't expose internals to client
        print(f"[PRisk] Unexpected error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal analysis error: {type(e).__name__}: {str(e)}"
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