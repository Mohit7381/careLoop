# careloop-service

Mohit's workstream from the CareLoop hackathon plan: **Orchestrator + Reporter + PRD + delivery + API**.

Wires together the 5-agent pipeline (Fetcher -> Analyst -> Code Scout -> Reporter -> PRD Generator -> Report Writer -> Delivery) as a sequential LangGraph `StateGraph`, exposes it over FastAPI, and owns the parts that are fully implemented here: the Reporter (trend deltas + narrative), the PRD generator, the Markdown report renderer, and Garuda GChat delivery (non-fatal on failure).

Fetcher (Alief), Analyst's LLM drill-down (Nakul), and Code Scout's GitLab search (Harshit) are stubbed with fixture data / hardcoded demo output so the whole pipeline runs end-to-end **today**, with clearly marked `TODO(<owner>)` seams for each to swap in real calls. The contract each stub must keep producing is in `app/schemas/contracts.py` — don't change field names there without syncing with the team.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # demo_mode works with zero env vars filled in
```

## Run

```bash
uvicorn app.main:app --reload --port 8077
```

```bash
# trigger a run (demo_mode=true reads app/fixtures/*.json)
curl -s -X POST localhost:8077/v1/analysis/runs \
  -H "Authorization: Bearer dev-local-token" -H "Content-Type: application/json" \
  -d '{"window_start":"2026-08-01","window_end":"2026-08-30"}'

# poll it
curl -s localhost:8077/v1/analysis/runs/1

# get the rendered markdown report
curl -s localhost:8077/v1/analysis/runs/1/report
```

## Test

```bash
pytest tests/ -q
```

`tests/test_pipeline.py` is the Day-1 gate: the whole graph runs on fixtures with no network calls and reproduces the known-good demo finding (51,321/wk payment-timeout kill -> `ConsultationDao.java:146` -> `missing_retention_hook`).

## Where to plug in real calls

| File | Owner | Replace |
|---|---|---|
| `app/pipeline/nodes/fetcher.py` + `app/integrations/metabase_client.py` | Alief | fixture loads -> real Metabase query pack |
| `app/pipeline/nodes/analyst.py` (`_call_analyst_llm_stub`) | Nakul | rule-based hypothesis -> sphere-platform LLM call + `aggregate()` drill-down loop |
| `app/pipeline/nodes/code_scout.py` + `app/integrations/gitlab_client.py` | Harshit | hardcoded gap -> real GitLab blob search |
| Everything else (orchestrator, Reporter, PRD generator, report writer, Garuda delivery, API) | Mohit | already real, not a stub |

## Config

See `.env.example`. Nothing beyond `APP_TOKEN` is required while `DEMO_MODE=true`.
