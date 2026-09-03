# CareLoop

**An autonomous engine that identifies and validates healthcare user journeys, then turns what it finds into evidence-backed, human-reviewed product recommendations.**

Built in a 2-day hackathon. Scope for this build is deliberately narrow: **PD / pharmacy delivery / pharmacy / health store** flows, start-to-payment and everything in between. No other verticals.

## Core insight

CareLoop automates a workflow the team already did by hand. Before writing any code, the team ran 12 warehouse queries manually, verified 3 gap findings, and traced one of them to a specific line of source code (`ConsultationDao.java:146`). This hackathon encodes that proven manual process into four cooperating agents — it does not invent a new analysis method, it automates one that was already validated.

Every output is a **proposal for human review**. Findings, code gaps, and PRDs are never auto-filed, auto-merged, or auto-shipped.

## Architecture — sequential pipeline

```
Fetcher  ──▶  Analyst  ──▶  Code Scout  ──▶  Reporter + Feature Generator ──▶  Delivery

```

Orchestrated as a **LangGraph `StateGraph`**, run sequentially, with a single shared state object (`RunState`) threaded through every node.

### Agent 1 — Fetcher (deterministic, no LLM)
Runs a versioned pack of read-only Metabase queries against Redshift (funnel counts, cancellation reasons, CT events) and ingests PII-scrubbed Play Store reviews. Ships a `demo_mode` that loads frozen, k-anonymized fixture data so the demo never depends on live warehouse latency.

### Agent 2 — Analyst (rules + agentic loop)
Three phases:
1. **Deterministic** — stage-to-stage conversion rates per segment, normalized cancellation-reason clustering, k-anonymity floor (n < 25 suppressed).
2. **Agentic drill-down** — for the top drop point, an LLM drives a whitelisted `aggregate()` tool (max 10 queries) to find a correlated pattern, explicitly labeled *correlation, never cause*.
3. **VoC corroboration + escalation** — each negative Play Store review gets one primary theme; a theme with >20 negative reviews becomes a VoC-originated finding in its own right, routed onward with pre-derived search terms.

An evidence validator rejects any finding without a citable number — "insufficient data" is a valid output; guessing is not.

### Agent 3 — Code Scout (novel; read-only)
The one step in the pipeline with no manual precedent — it connects a funnel finding to the exact line of code responsible for it.

- Routes each finding to its owning repo via a static table (`RoutingStage → repo`):
  - `consultation` → `bintan/consultation`
  - `pharmacy_checkout` → `timor/oms`, `timor/fulfilment`
  - `payments` → `scrooge/payment-service`
  - `re_engagement` → `transformers/garuda`
- Proposes 3–5 search terms per finding (the `code-gap-assessment` sphere-platform use case), searches GitLab, fetches the matching file, and pins the exact line.
- Classifies every resolved gap as one of `logic_flaw | missing_retention_hook | ux_gap` — this classification is what makes the generated PRD's proposed fix specific instead of generic.
- `mechanism_found=False` is a first-class, schema-validated outcome, not an error — a search that finds nothing is reported honestly, never papered over with a fabricated location.
- Hard constraint: read-only PAT everywhere. Names `file:line`. Never writes a diff, never opens an MR.

**Status: implemented and test-verified**, including a live reproduction of the proven example (`bintan/consultation` → `ConsultationDao.java:146`, constant `GET_ABANDON_CONSULTATION`) against the real GitLab instance. Currently lives at `~/dev/halodoc/careloop-service` pending merge into the shared repo — see [Current status](#current-status) below.

### Reporter + Feature Generator + delivery
Computes period-over-period deltas (funnel, feature adoption, VoC theme trends), turns them into a short business narrative, then fills an 8-section PRD template from findings + code gaps + trends + VoC quotes (≤2 quotes, always labeled anecdotal). Stamped `DRAFT — needs human review`. Delivered to the UI and a GChat channel via Garuda; a human clicking Approve is what makes it real.

### UI
A Claude Design prototype wired to `GET /v1/analysis/runs/{id}`, showing the pipeline stages lighting up in sequence, the drill-down trail playing live, the code-location "money moment," and the VoC "human moment."
