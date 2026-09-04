# CareLoop

**An autonomous engine that identifies and validates healthcare user journeys, then turns what it finds into evidence-backed, human-reviewed product recommendations.**

## High-level architectural workflow

```
Fetcher ─▶ Analyst ─▶ Code Scout ─▶ Suggestion ─▶ Reporter ─▶ PRD Generator ─▶ Report Writer ─▶ Delivery
```

- **Fetcher** — data aggregation layer, brings data from various sources.
- **Analyst** — funnel-gap detection → agentic drill-down → VoC classification/escalation/corroboration → LLM correlation pass.
- **Code Scout** — routes a finding to its repo, locates the mechanism, runs the Remedy Loop (verifies ≤3 proposed fixes against source). Read-only.
- **Suggestion** — Code Scout's generative sibling: proposes business/tech/process improvements per finding.
- **Reporter** — period-over-period deltas + narrative.
- **Feature Generator** — one draft PRD per finding from findings + gaps + suggestions + trend + quotes. Always stamped `DRAFT`.
- **Report Writer** — renders the Markdown report.
- **Delivery** — sends to Garuda, only after a human clicks Approve.

## Steps to host the changes locally

### Prerequisites

- Python ≥3.10
- Node — Angular CLI 22 wants ≥22.22.3/24.15.0/26.0.0. In practice it also boots (with a version warning) on Node 20, verified locally; if `npm start` fails outright rather than just warning, upgrade Node.

### Backend

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

### Trigger a run and read its output

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

### UI

```bash
cd root/ui
npm install
npm start                                        # ng serve, fixture mode - http://localhost:4200/runs/47
# or, against your local backend from step 1:
npm start -- --proxy-config proxy.conf.json      # then open http://localhost:4200/runs/1?live=1
```
