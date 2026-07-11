# PRisk — Tests, CI & Self-Protection (v1.7.0)

The tool that recommends tests now has its own, and the open endpoint can no longer be drained.

## Test suite (`backend/tests/`, 40+ assertions, no network/LLM needed)

- `test_scoring.py` — determinism, score bounds, breakdown-sum consistency, monotonicity (worse impact ⇒ lower score), security-finding penalties, measured-dependents effects, hotspot penalties, tests-in-diff credit, recommendation bands, driver provenance.
- `test_normalize.py` — every normalizer survives `None`/garbage; string-vs-object finding shapes; enum defaults; score clamping.
- `test_dependency_graph.py` — synthetic multi-language repo: Python/Java/TS import detection with line citations, no false positives, self-imports excluded, soft failure.
- `test_urls_and_secrets.py` — PR URL parsing accept/reject matrix; token scrubbing.
- `test_payload_and_quality.py` — full response contract; analysis-quality modes.
- `test_history_mining.py` — real temp git repo: fix-commit counting, hotspot flagging (skips if git absent).

## CI (`.github/workflows/ci.yml`)

- Every push/PR runs backend pytest (Python 3.12) + the frontend **production build** — the exact check Vercel runs, so budget/type errors are caught before deploy, and rounds I can't verify locally get verified automatically.

## Self-protection

- **Per-IP rate limit** on both analyse endpoints (default 10 analyses / 10 min; `RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW_SECONDS`). Friendly 429 with retry guidance; the UI shows "Taking a short breather" instead of a raw error.
- **Per-commit cache**: same PR + same head SHA ⇒ instant cached report, zero LLM calls (default TTL 24h, `CACHE_TTL_SECONDS`, LRU 100 entries). A new push changes the SHA and naturally re-analyses. The stream emits "This commit was already analysed — returning the saved report…". The duplicate GitHub fetch was avoided by letting `build_repository_context` accept pre-fetched PR data.

---

# Decide → Prove → Act (v1.6.0)

The report is no longer organized around the pipeline — it's organized around the decision.

- **Decide**: a "Why this score" strip appears first — the three signals that moved the PRisk Score most, as cards with signed points (red = lost, green = earned). No drawer-opening required to understand the number.
- **Prove**: the evidence — Measured Dependents citations, file risk pins, historical fix/revert records — is promoted out of the Blast Radius accordion to a permanent top-level "Evidence" zone that can never be collapsed. The product's moat is now the second thing every user sees.
- **Act**: a "Do these first" ranked list — priority tests and Critical/High/quick-fix findings with **estimated score impact** ("≈ +4 pts"), honestly derived by splitting each dimension's current point deficit across its actions. This creates the loop: fix → re-analyse → score rises.
- **Full report**: the original five sections remain, unchanged, under a labeled divider — depth for those who want it, no longer a prerequisite for understanding.
- **Named metric**: the gauge is now titled "PRisk Score" and the Markdown export leads with `PRisk Score: N/100` — the string that spreads in PR threads.
- **Landing story**: the idle state is now a hero — "Merge with receipts" with three proof pillars (Measured / Remembered / Explained) and a no-signup CTA, replacing the feature-listing empty state.
- Note: sandbox unavailable this round — verified by manual review; run `ng build` before deploying.

---

# Dark Mode (v1.5.1)

- **Full dark theme**, same teal identity on deep blue-gray surfaces (`#0e1519` base). One `[data-theme='dark']` token override — every component adapts automatically because the entire UI reads from CSS variables.
- **Sun/moon toggle** in the header; choice persists in localStorage; first visit follows the OS `prefers-color-scheme`. An inline pre-boot script in `index.html` applies the theme before Angular loads, so there's no light-mode flash.
- Remaining hardcoded colors migrated to tokens (`--track`, `--skeleton-*`, `--card-overlay`, `--gauge-track`, `--action-*`, `--critical`) so meters, skeletons, the gauge ring, primary buttons, and the Critical chip all render correctly in both themes. `color-scheme` set per theme so native scrollbars/inputs match.
- Note: final compile check for this round was reviewed manually (sandbox disk full); run `ng build` locally before deploying.

---

# Provable Blast Radius (v1.5.0)

The moat. Every competitor's dependency claim is an LLM opinion — PRisk now **measures** it.

- **Deterministic dependency graph** (`core/dependency_graph.py`): scans the cloned repo's import statements (Python `import`/`from`, Java `import`, JS/TS `import`/`require`) and finds the exact files that import what the PR changed — with **line-number citations of the actual code**: `gateway/routes/api.py:2 — from services.hotel_service import HotelService`. Capped scans (4000 files, 300KB each), vendored dirs skipped, false-positive guards on generic names.
- **Score integration**: when the graph is available, the AI's impact opinion carries less weight (0.42 vs 0.55) and measured dependents carry real weight. Zero measured dependents *earns points back* ("Import scan found no files depending on the changed code: +2.0"). Drivers say "4 files measurably import the changed code: −4.3".
- **Agent 2 grounding**: the blast-radius agent receives the measured edges labeled "treat as ground truth" — it explains around evidence instead of inventing dependents.
- **UI**: new "Measured Dependents" block at the top of the Blast Radius panel with a "Proven from imports" tag, per-file citation rows (`file:line` + the import code itself); the AI's chains are now explicitly tagged "AI-inferred". The zero-dependents case renders as a green measured-safe block. Markdown export includes the citations.
- New streaming stage: "Mapping the import graph — measuring real dependents…"
- Verified against a synthetic multi-language repo: Java import, both Python import styles, and JS `require` detected with correct citations; unrelated files not flagged; end-to-end context build emits the graph stage and scoring reflects measured dependents.

---

# Honest Failures (v1.4.4)

- **No more silent fallback (strict mode).** If the AI provider fails (rate limit, bad key, dead model), agents 1–4 now abort the whole analysis with a 503 and a plain-language reason ("rate limit reached — try again in about a minute") instead of presenting heuristic guesses as results. The UI states explicitly: *"Nothing was scored or guessed."* Heuristic report generation is gone; a report you see is always a real AI analysis. (Agent 5's prose fallback remains — it never affects the score.)
- **Clear URL errors.** Invalid links are caught client-side before any request: the input gets a red ring, and a structured error card shows a title, explanation, and the expected format as a code chip. Nonexistent PRs return "Pull request not found: owner/repo #N — check the repository name and PR number" instead of GitHub's bare "Not Found".
- **Full path on hover.** Truncated file paths in risk pins and history evidence show the complete path in a tooltip.

---

# Panel Interiors (v1.4.3)

- Every expanded section rebuilt from "stacked labeled boxes" into a scannable layout: a **stat strip** on top (segmented metrics with dividers — change type/lines/complexity/files; impact/downstream/modules/flows; severity/issues/clear-categories; coverage/count/test types), a **lede** summary line with brand accent instead of a boxed paragraph, and **two-column grids** for related detail blocks.
- **Dependency chains are now visual**: `configServer → serviceRegistry → hospitalService` renders as monospace node chips connected by arrows instead of ASCII text in bullets.
- Bullet walls replaced with **accent lists** (square teal markers), list labels carry **count pills** ("Missing Tests ⑤"), positive notes became a green "What Was Done Well" block, and priority tests are headed "Write These First". Stat strips collapse to a 2-per-row grid on mobile.

---

# Header Scorecard (v1.4.2)

- Section headers upgraded from bare adjective pills to a scorecard: each header now shows a contextual verdict pill ("Medium impact", "High severity" instead of ambiguous "Medium"/"High"), the **points that dimension contributed** ("21/40"), and a tone-colored mini-meter. The Merge Confidence header shows the recommendation instead of duplicating the gauge's percentage. Collapsed sections now read as a complete scorecard without opening anything. Score cell hides on narrow screens to avoid clutter.

---

# Instant History Snapshots (v1.4.1)

- Clicking a recent analysis now opens the **saved report instantly** (full report cached in localStorage) instead of re-running the whole pipeline. A brand-tinted bar shows "Saved snapshot from Xm ago — the PR may have new commits since" with an explicit **Re-analyse now** button, preserving the score-delta loop as a deliberate action.
- Storage quota safety: if localStorage is full, history falls back to storing score metadata only (old behaviour — clicking those re-runs).

---

# Trust Refactor (v1.4.0)

Round 4: the score is now deterministic, granular, explainable, and honest about how it was produced.

## Root cause of the "identical 57" bug — fixed

- **Groq deprecated `llama-3.3-70b-versatile` (June 17, 2026)** for free/developer tiers. Every LLM call failed; all five agents silently fell back to heuristics; similar PRs bucketed to identical scores. Default model is now **`openai/gpt-oss-120b`** (Groq's recommended migration). ⚠️ **Action needed:** if `GROQ_MODEL` is set to the old model in your local `.env` or Render environment variables, remove or update it.

## New scoring engine (`core/scoring.py`)

- **Deterministic**: no LLM in the arithmetic — same inputs always produce the same score. Weights unchanged (Blast 40 / Eng 30 / Test 20 / Complexity 10), bands unchanged (80/60).
- **Granular**: continuous math over measured quantities — real diff line counts (not the LLM's estimate), severity-weighted finding loads (Critical 1.0 / High .55 / Medium .25 / Low .10, security ×1.5, saturating curve), downstream-service counts, file breadth, hotspot history. Two different PRs virtually never tie.
- **Evidence-blended**: AI judgment sets each dimension's base; hard facts (test files present in the diff, git fix history, measured size) move it. Clean git history now *earns* points back.
- **Explainable**: every dimension returns `score_drivers` — the exact signals and the points each cost or restored. Rendered in the Merge Confidence breakdown cards and in the Markdown export ("Why these scores").
- Verified: a small guarded fix scored **88 (Safe to Merge)** while a broad no-test routing refactor scored **60 (Needs Validation)** — in fully degraded (no-LLM) mode, where the old system returned identical 57s.

## Honest degradation

- **`invoke_llm_json` / `invoke_llm_text`** (`core/llm.py`): single validated path for all agents — retry on transient failure, JSON parsing, required-key schema checks. A half-formed AI answer can no longer silently enter the report.
- **`analysis_quality`** in every response: `full` / `partial` / `degraded`, with the list of agents that fell back and a plain-language note. The UI shows an amber/red banner when the analysis wasn't fully AI-powered, and the Markdown export carries the same warning. Silent fallback is gone.
- Agent 5's executive summary is now written *from the computed drivers* — the narrative can no longer contradict the number. (Its fallback only affects prose, never the score.)

---

# Round 3 — Evidence Engine (v1.3.0)

Round 3: the standalone-maker. Risk claims are now backed by git evidence, and findings carry severity + effort.

## Historical Risk Evidence (new signal)

- **`mine_history_risk`** (`core/context_builder.py`): clones now fetch recent history (`CLONE_DEPTH`, default 300 commits, single branch) and mine it per changed file — total changes, fix/revert/hotfix commit count, days since last touch, distinct authors. One `git log` subprocess; adds ~1–3s.
- **Hotspots**: files with ≥2 fix-commits are flagged. Any hotspot ⇒ overall history level High.
- **Agent 2 grounding**: the blast-radius agent now receives the evidence table in its prompt and is told to weigh empirically fragile files when setting `impact_level`. The 40/30/20/10 scoring formula is unchanged.
- **UI**: new "Historical Risk Evidence" block in the Blast Radius panel (per-file fix/change counts, recency); file pins gain a red **Hotspot** state alongside Epicenter; new "Mining commit history…" streaming stage; evidence included in the Markdown export.
- Fails soft: if history can't be read (or clone failed), `history_risk.available=false` and the UI simply omits the block.

## Severity-first findings

- **Agents 3 & 4 return structured findings**: engineering issues are now `{text, severity: Critical|High|Medium|Low, effort: "Quick fix"|"Needs thought"}`; priority tests are `{text, effort: Easy|Medium|Involved}`.
- **Normalization accepts both shapes** (strings from heuristic fallbacks or objects from LLMs) — old outputs still render, no regression. Security findings default to High severity when unspecified.
- **Engineering panel redesigned**: findings grouped under severity headings (worst first) as cards with a colored severity edge, category tag, and effort chip; clean categories shown as ✓ chips; a proper "No issues found" state.
- **Verified**: live run shows the history stage streaming, correct per-file evidence (README in octocat/Hello-World: 2 changes, 2 authors, ~15 years old), normalization unit-checked, Angular AOT typecheck zero errors.

---

# Round 2 — Startup-Grade Rebuild (v1.2.0)

Round 2: full visual rebuild + three differentiator features. Same product, same pipeline, same hosting.

## New features

- **Copy report as Markdown** (`services/report-export.ts`): one click in the results header copies the entire analysis as GitHub-flavoured Markdown — score table, blast radius, prioritized tests in a collapsible section — ready to paste into the PR conversation. Button confirms with "Copied — paste into the PR".
- **Recent analyses with score deltas** (`services/history.service.ts`): the sidebar remembers the last 8 analyses (localStorage). Re-analysing the same PR after pushing fixes shows the delta ("▲ +17") — the analyse → fix → re-check → merge loop made visible. Click any entry to re-run it.
- **File-level risk pins** (dashboard, Blast Radius panel): every changed file is cross-referenced against the blast-radius modules; matching files are flagged **Epicenter** — review these first. Backend now returns `changed_files` in the payload (backward-compatible addition).

## Visual rebuild (same identity, elevated)

- **Design system** (`styles.css`): full CSS token set — ink/brand/semantic color scales, elevation shadows, radii, motion curve — plus styled selection, scrollbars, and `prefers-reduced-motion` support.
- **App shell**: gradient brand mark with radar logo, tagline, pill status chip with pulsing dot while running, ambient radial-gradient backdrop.
- **Animated confidence gauge**: the score is now an SVG ring that sweeps to its value (tone-colored), replacing the static number box.
- **Dashboard**: per-section icons (diff/radar/brackets/flask/shield), staggered card entrance, refined badges and tokens in brand tints, monospace file paths, smoother expand animation.
- **SVG favicon** with the radar mark (data URI, no asset needed).

---

# Round 1 — Code Quality + Streaming (v1.1.0)

No hosting changes (still Vercel + Render), no changes to the 5-agent pipeline logic, scoring formula, or product terminology. The classic `POST /api/analyse` endpoint is unchanged in shape and kept as the streaming fallback, so nothing regresses.

## Security fixes

- **GitHub token leak (high severity).** When a repo clone failed, GitPython's error message — which embeds the full `https://x-access-token:<TOKEN>@github.com/...` URL — was appended to `errors` and returned to the client. Added `scrub_secrets()` in `core/context_builder.py`; it is now applied to every error string that can reach a client (clone errors, HTTP error details, log output). Verified with a live test.
- **Internal error exposure.** The 500 handler previously returned `type(e).__name__: str(e)` to the client despite a comment saying otherwise. It now logs full (scrubbed) tracebacks server-side and returns a generic message.
- **Input hardening.** `pr_url` now has `min_length=1, max_length=500` at the Pydantic layer.

## Correctness / robustness fixes

- **Event-loop blocking.** `POST /api/analyse` was `async def` but ran a 30–60s fully synchronous pipeline (GitHub API, git clone, LLM calls), freezing the entire server for every concurrent user. It is now a sync `def`, which FastAPI runs in its threadpool.
- **Agent output normalization (`core/normalize.py`, new).** LLM JSON is unpredictable — missing keys, strings where ints belong, strings where lists belong. Previously this flowed raw into Angular bindings (e.g. `affected_module.split(',')` would throw on a missing key and blank the dashboard). Every agent output now passes through a normalizer that guarantees the full response shape.
- **Frontend crash guards.** `affected_module.split()` moved into a null-safe `affectedModules` getter; removed stray `console.log` of the full result.
- **Zoneless change detection.** App state was plain fields patched with `NgZone.run()`/`detectChanges()` hacks. Converted to Angular signals (`state`, `result`, `errorMessage`, `progressSteps`) — correct by construction in a zoneless app, including updates arriving from stream callbacks. Removed the redundant `HttpClientModule` import (`provideHttpClient` already configured).
- **Double-submit guard.** Enter/click during a running analysis no longer fires a second request; input and button disable while loading.
- **Production error copy.** "Is FastAPI running on port 8000?" no longer shown to production users; now mentions the Render cold-start possibility instead.
- **CORS via env.** Extra allowed origins (e.g. Vercel preview URLs) can be added with an `ALLOWED_ORIGINS` env var on Render — no code change needed. Stale comment fixed.

## New: live streaming status (SSE)

- **`POST /api/analyse/stream`** (`main.py`): streams `status` events while the pipeline runs, then a final `result` (or `error`) event. Runs the pipeline in a worker thread with a queue feeding an async SSE generator; sends `: keep-alive` comment frames every 15s so proxies don't drop the connection during long LLM calls. `X-Accel-Buffering: no` disables proxy buffering.
- **Stage events from the context builder** (`core/context_builder.py`): validate → fetch PR → read diff (with file count) → clone → summarise.
- **Node-level agent progress** (`core/workflow.py`, `stream_analysis()`): uses LangGraph's `.stream(stream_mode="updates")` to emit an event as each agent node completes — including the three parallel agents finishing independently.
- **Frontend** (`analysis.service.ts`): `analysePRStream()` POSTs via `fetch()` and parses SSE frames off the response body (EventSource can't POST). If the stream transport fails before any event, the app automatically falls back to the classic invoke-and-wait endpoint.
- **UI**: a calm "Live analysis" trace below the URL input — one line per stage, teal pulsing marker on the active step, green dots for completed steps, connected by a hairline. The results column shows a shimmer skeleton of the five sections while streaming.

## Visual/UX polish (same theme, refined)

- Inter is now actually loaded (it was referenced in CSS but never linked) with preconnect.
- `index.html`: real title ("PRisk — Pull Request Risk Intelligence"), meta description, theme color — was "Frontend".
- Analyse button shows an inline spinner + "Analysing…" while running.
- Empty state gets a radar-motif icon in the theme teal; error/empty copy unchanged.
- Section expand animation, subtle card hover elevation, `focus-visible` rings on buttons, disabled-input styling, tightened heading letter-spacing.
- Removed duplicated comment blocks in the dashboard template.

## Verification performed

- Backend run live in a sandbox (GitHub API stubbed — sandbox network restriction — but real repo clone, real LangGraph run with heuristic fallbacks): all 12 stream events arrive in order, final payload correct (score 92 / Safe to Merge for a 1-file test diff), invalid URLs return a 400-style `error` event on the stream and HTTP 400 on the legacy endpoint, and clone-failure errors contain `***` in place of the token.
- Frontend: full Angular AOT typecheck (`ngc`, `strictTemplates`) passes with zero errors.
