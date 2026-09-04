# CareLoop

**An autonomous engine that identifies and validates healthcare user journeys, then turns what it finds into evidence-backed, human-reviewed product recommendations.**

Built in a 2-day hackathon. Scope is deliberately narrow: **PD / pharmacy delivery / pharmacy / health store** flows, start-to-payment and everything in between.

## Core insight

CareLoop automates a workflow the team already did by hand. Every output is a **proposal for human review** — findings, code gaps, suggestions, and PRDs are never auto-filed, auto-merged, or auto-shipped. A human clicking Approve is what makes any of it real.

## High-level architectural workflow

CareLoop is a **sequential LangGraph pipeline** — eight nodes, one shared state object (`RunState` / `GraphState`) threaded through all of them, each node validating its slice against `app/schemas/contracts.py` at its boundary so a bad shape fails loudly instead of corrupting state silently downstream.

```
Fetcher ─▶ Analyst ─▶ Code Scout ─▶ Suggestion ─▶ Reporter ─▶ PRD Generator ─▶ Report Writer ─▶ Delivery
 (Alief)    (Nakul)     (Harshit)     (Harshit)     (Mohit)       (Mohit)         (Mohit)        (Mohit)
```

| # | Node | What it does |
|---|---|---|
| 1 | **Fetcher** | Pulls the funnel snapshot (stage conversions, cancellation reasons, CT events) and PII-scrubbed Play Store reviews for the run's journey/window. Demo mode reads frozen fixtures; live mode raises `NotImplementedError` today — the real Metabase query pack and Play Store scraper aren't wired yet. |
| 2 | **Analyst** | Three-and-a-half phases, in order: (1) **deterministic** funnel-gap detection with k-anonymity suppression; (2) **agentic drill-down** — an LLM drives a whitelisted `aggregate()` tool (budgeted) to find a correlated pattern, always labeled *correlation, never cause*; (2.5) **semantic VoC classification** — every negative review gets one theme, via an LLM call (`voc-theme-classification`) rather than pure keyword matching, and large unescalated themes are shown to the drill-down model as `voc_signals` context; (3) **corroboration + escalation** — a theme clearing the escalation threshold becomes its own VoC-originated finding; a theme sharing a warehouse finding's exact routing stage corroborates it; (3.5) **LLM-driven correlation** — a further pass that reasons over finding hypothesis vs. theme content to catch correlations the stage-equality lookup structurally misses (e.g. a review theme filed under a different stage that plausibly describes the same failure). An evidence validator rejects any finding without a citable number. |
| 3 | **Code Scout** | Routes each finding to its owning GitLab repo via a static routing table, searches for the responsible mechanism, and runs the **Remedy Loop**: proposes ≤3 code-verifiable fixes and verifies each against the source (`exists` / `absent` / `partial`). Read-only — never writes a diff, never opens an MR. Output: `CodeGap`. |
| 4 | **Suggestion** | Code Scout's generative alternate flow: explores the repo and proposes zero-to-several **tech / business / process** improvements per finding (not just code fixes), each independently verified where a code claim applies. Runs alongside Code Scout, not instead of it — a finding can produce a `CodeGap`, `Suggestion`s, both, or neither. |
| 5 | **Reporter** | Computes period-over-period deltas (funnel, feature adoption, VoC theme trends) and turns them into a short business narrative. |
| 6 | **PRD Generator** | Drafts one PRD per finding (capped) from findings + code gaps + suggestions + trend + VoC quotes (≤2 quotes, labeled anecdotal). Functional requirements are numbered across *both* code fixes and suggestions in one list — a business idea is just as valid an FR as a code fix. Stamped `DRAFT — needs human review`. |
| 7 | **Report Writer** | Renders the run's Markdown report artifact. |
| 8 | **Delivery** | Sends the report to Garuda (GChat/WhatsApp/etc.) — a human clicking **Approve** in the UI is what actually triggers this; the pipeline never auto-delivers. |

**Cross-cutting bits:**
- **Journeys are config, not code** — `config/journeys/{pd_checkout,consultation}.yaml` each define their own funnel stages, routing categories, VoC theme lexicon, and drill-down dimensions. Adding a journey is a config drop.
- **Scoped runs** — `POST /v1/analysis/runs` accepts a free-text `prompt` ("just look at the payments funnel") resolved into a `RunScope` that narrows drill-down dimensions and the funnel transition analyzed, without touching the underlying journey config.
- **Demo vs. live** are two independent switches: `DEMO_MODE` controls the *data source* (frozen fixtures vs. real warehouse/reviews — Fetcher's live path isn't built yet, so this is effectively always fixture data today), and `LLM_MODE` / `LIVE_LLM` control whether LLM calls hit the real sphere-platform or replay a recorded session. Every sphere use case has a `make_use_case_llm()` factory that resolves to `None` gracefully (never a crash) when a use case isn't provisioned yet, rather than raising mid-run.
- **The UI** ([`root/ui`](root/ui), Angular) renders `RunState` end-to-end: pipeline tracker, funnel, findings, drill-down trail, the VoC "Users say" panel, the Code Scout/Suggestion panels with per-item verification chips, and a PRD drawer with in-place editing, chat-based edits, and a client-side `.docx` export.

## Exact steps to host the changes locally

### Prerequisites

- Python ≥3.10
- Node — Angular CLI 22 wants ≥22.22.3/24.15.0/26.0.0. In practice it also boots (with a version warning) on Node 20, verified locally; if `npm start` fails outright rather than just warning, upgrade Node.

### 1. Backend

```bash
git clone <this repo> && cd careLoop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # demo mode needs zero real credentials filled in
```

Run it on **port 8000** — the UI's committed proxy config expects the backend there:

```bash
uvicorn app.main:app --reload --port 8000
```

A local `careloop.db` (SQLite) is created automatically on first startup and auto-migrated on every subsequent startup as new columns get added upstream (`init_db()`'s `_ensure_column` backfill) — you don't need to delete it after a `git pull`. If something ever gets into a state `_ensure_column` can't fix, just `rm careloop.db` and restart; it's rebuilt from scratch.

### 2. Trigger a run and read its output

```bash
# trigger a run (journey defaults to pd_checkout; demo mode reads fixtures/pd_checkout/*.json)
curl -s -X POST localhost:8000/v1/analysis/runs \
  -H "Authorization: Bearer dev-local-token" -H "Content-Type: application/json" \
  -d '{"window_start":"2026-08-27","window_end":"2026-09-02"}'
# -> {"run_id": 1, "status": "queued", "journey": "pd_checkout", "scope": {...}, ...}

# poll it (no auth needed on GETs) until status is "completed"
curl -s localhost:8000/v1/analysis/runs/1

# get the rendered Markdown report / PRD for that specific run id
curl -s localhost:8000/v1/analysis/runs/1/report
curl -s localhost:8000/v1/analysis/runs/1/prd
```

**Important:** each run gets a new, permanent `run_id`; `GET /runs/{id}/report` only ever reads that run's own frozen artifact file from `data/artifacts/{id}/` — it never recomputes. If you change code and want to see the effect, you must `POST` a new run and read *its* id, not re-fetch an old one.

### 3. Run the tests

```bash
pytest -q
```

`tests/test_pipeline.py` is the Day-1 gate: the whole graph runs on fixtures with no network calls and reproduces the known-good demo findings.

### 4. UI

```bash
cd root/ui
npm install
npm start                                        # ng serve, fixture mode - http://localhost:4200/runs/47
# or, against your local backend from step 1:
npm start -- --proxy-config proxy.conf.json      # then open http://localhost:4200/runs/1?live=1
```

Fixture mode needs no backend at all. Live mode polls the real API every 1.5s until the run completes/fails, and falls back to the fixture (with a `source:` chip explaining why) on any failure rather than mixing live and fixture data on one screen. See [`root/ui/README.md`](root/ui/README.md) for the full UI-specific details (edit modes, known contract gaps, build/test commands).

### 5. Going live (real LLM / real integrations)

Demo mode (the default) needs none of this. To point any piece at a real backend:

| Integration | Env var(s) that actually work | Owner |
|---|---|---|
| Sphere-platform LLM | `LLM_MODE=sphere`, `SPHERE_APP_TOKEN=...`, optionally `SPHERE_BASE_URL=...` (read directly from the shell environment by `app/integrations/sphere.py`, **not** through `.env`'s `SPHERE_PLATFORM_*` keys — see gotcha below) | — |
| Force real LLM calls even in demo mode | `LIVE_LLM=true` | — |
| GitLab (Code Scout) | `GITLAB_READ_TOKEN` in `.env` (`GITLAB_BASE_URL` is already the real self-hosted instance) | Harshit |
| Metabase (Fetcher) | not wired yet — live mode raises `NotImplementedError` regardless of env vars | Alief |
| Garuda (Delivery) | `GARUDA_*` in `.env` — `channel_id`/`provider_id`/`template_id` must already be provisioned in Garuda itself; GChat as a channel type is unconfirmed | Mohit |

**Known gotcha:** `.env.example`'s `SPHERE_PLATFORM_BASE_URL`/`SPHERE_PLATFORM_API_KEY` don't currently wire to anything — the live sphere client reads `SPHERE_BASE_URL` and `SPHERE_APP_TOKEN` directly from the process environment first, falling back to the `sphere_platform_app_token` *setting* (which itself maps from `SPHERE_PLATFORM_APP_TOKEN`, not `_API_KEY`). If you're enabling live LLM calls, export `SPHERE_APP_TOKEN` and `SPHERE_BASE_URL` directly rather than relying on `.env`.

### Config reference

See `.env.example` for the full list. Nothing beyond `APP_TOKEN` is required while `DEMO_MODE=true` (the default).
