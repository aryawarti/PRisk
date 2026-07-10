# PRisk — Startup-Grade Rebuild (v1.2.0)

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
