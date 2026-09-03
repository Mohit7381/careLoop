# CareLoop UI

Angular implementation of Screens 1–3 (Runs dashboard, Run detail, PRD draft) from the CareLoop Build Plan's design prompt. Renders `RunState` — the shared state contract in [`app/schemas/contracts.py`](../codeScout/app/schemas/contracts.py) — as the funnel, findings, drill-down trail, "Users say" panel, and Code Scout's explored-and-suggested output (Rev 3), plus a PRD drawer with a client-side `.docx` export.

## What's implemented

- **Screen 1 — Runs dashboard** (`features/runs-dashboard`): a static past-runs table + "New analysis". Minimal on purpose — the design prompt gives it five seconds of demo time and none of the script's beats happen here.
- **Screen 2 — Run detail** (`features/run-detail`): the main screen. Pipeline tracker (4 stages) → funnel → findings (ranked, origin-badged) → drill-down trail + "Users say" nested under finding #1 → Code Scout panel (Rev 3: grouped by finding, tech/business/process suggestions, each independently verified).
- **Screen 3 — PRD drawer** (`features/run-detail/components/prd-drawer`): renders the backend's real `prd_markdown`, split into editable sections. **Edit** turns each section into an in-place editor with the same layout; sections can be added, reordered, deleted and reverted. Falls back to a structured view built from findings + code_gaps only when a run has no `prd_markdown`. Plus **Approve & send to GChat**, **Request changes**, **Download .docx** (exports whatever is currently on screen, edits included).
- **Human edits never look like agent output.** An edited or added section is badged `EDITED/ADDED BY YOU · UNVERIFIED`, tinted, and counted in a banner saying the changes are not verified against the code. Agent requirements carry a Remedy Loop verdict; typed ones carry none, and nothing in the UI promotes one to the other. Edits are session-only — `POST /v1/analysis/runs/{id}/prd/revisions` does not exist, so a reload restores the generated document.
- **Demo playback** (`core/services/demo-playback.service.ts`): the "Replay run" animation — hard-coded timer beats, not real backend progress, so every rehearsal runs identically. Ported from the original HTML prototype.
- **`.docx` export** (`core/services/docx-export.service.ts`): builds a real OOXML `.docx` in-browser via JSZip — no backend endpoint, no round-trip.
- **contracts.py alignment**: `core/models/run-state.ts` is a hand-written TypeScript mirror of `contracts.py` — same field names, same shapes (`Finding.segments` as `{dimension,value}[]`, `Finding.evidence` as `{type,metric,value}[]`, `Suggestion.verification_status` with the tech-only / evidence-required either-ors from `model_post_init`, `RoutingStage` as an exact-match routing category, not a funnel-stage id). Do not rename anything here without syncing with Nakul/Harshit, same rule as the Python side.
- **Code Scout Rev 3 (2026-09-03): `code_gaps` → `suggestions`.** Code Scout's job changed from diagnosing one bug per finding to exploring a repo and proposing zero to several tech/business/process suggestions, each independently verified (`exists` / `absent` / `partial` / `not_applicable`). `code-scout-panel.component` renders this as one group per finding: an "Explored" code block (see contract gap #5 below), then a suggestion card per proposal with a type badge and verification chip. `CodeGap`/`GapClass`/`NoMatchReason` are kept in `run-state.ts` for reference only, mirroring `contracts.py` marking them SUPERSEDED rather than deleting them.
- **The `partial` verification state is the interesting one to point at on stage**: finding #2's "Reuse the existing communication hook" suggestion is genuinely `partial`, not `exists` — `sendCommunication` is real (`BaseCancellationTypeAdapterService.java:216`) but 82 lines from the mechanism it would need to be wired into (`abandonOrderV2`, line 298), past `VERIFICATION_PROXIMITY_LINES` (15) in `node.py`. This also corrects my Rev 2 fixture, which pointed at the wrong sibling method (`cancelOrderAndNotifyUser`, line 208) and carried an "unconfirmed" caveat as a result.

## Fixture data — what's real vs. illustrative

`core/fixtures/run-47.fixture.ts` is `run #47`, pharmacy delivery, 2026-08-26 → 2026-09-02. Provenance is documented at the top of that file; summary:

| Section | Source |
|---|---|
| `snapshot`, `findings`, `drilldown_trail`, `voc` | The 7-day hand-run (2026-09-02), k≥25 suppression applied at fetch — matches the Build Plan's design prompt verbatim |
| `suggestions` for finding #1 (`bintan/consultation`) | Copied from `impl/codeScout`'s `fixtures/code_scout/gap1_consultation.json` (Rev 3) — a **live** GitLab search, verified 2026-09-03. 2 suggestions: 1 tech (`absent`), 1 business. |
| `suggestions` for finding #2 (`timor/oms`) | Copied from `gap2_pharmacy_checkout.json` (Rev 3) — **corrects** my earlier Rev 2 fixture. The real mechanism is `abandonOrderV2` (`BaseCancellationTypeAdapterService.java:298`, the method the timer-driven `AbandonOrderService` actually calls) — zero notification calls in its body. 3 suggestions: 2 tech (one `absent`, one **`partial`** — `sendCommunication` exists at line 216 but 82 lines from `abandonOrderV2`, past the 15-line verification proximity), 1 business. |
| `suggestions` for findings #3, #4 | Empty — Code Scout hasn't explored `scrooge/payment-service` for these specific findings. `impl/codeScout`'s `gap3_synthetic_not_found.json` and `gap4_payment_link_expiry.json` exist but don't correspond to this run's finding #3/#4 topics (see their own `_verified` notes — gap3 is explicitly synthetic, gap4 is used only by `simulate_run.py`). Left empty rather than fabricated. |
| `trend_report` | Illustrative/empty — no previous-window figures were published for pharmacy delivery. The Reporter node hasn't shipped, so there's no trend section in this build (`SHOW_TREND` equivalent removed entirely rather than shown empty). |

## Known contract gaps

Found while wiring the UI to `contracts.py` v2/v3 — raise before relying on the affected feature, don't work around them silently in a second place:

1. **`VocQuote` has no `gloss` field.** The design prompt's "Users say" panel needs an English gloss under each Indonesian quote (the human moment). Kept as a client-side lookup keyed on quote text (`core/data/voc-gloss.ts`) rather than inventing a contract field unilaterally. Add `VocQuote.gloss` to `contracts.py` and this becomes dead code.
2. **`RunStatus` has no per-stage state**, only one global field: `queued | extracting | analyzing | reporting | completed | failed`. `reporting` jumps SCAN SERVICE CODE straight to `done` and nothing distinguishes PRD drafting — so **the live path can never animate the money moment**; only the fixture-mode "Replay run" can, because it fakes the timing. See the doc comment on `STATUS_MAP` in `run.service.ts`. Fix is two more enum values (`scanning`, `drafting`) plus each LangGraph node stamping its own status.
3. **`POST /v1/analysis/runs/{id}/deliver` doesn't exist.** The Approve button is wired against it (`RunService.deliver()`), but there's no backend route yet, and no verified example shows a GChat channel type in the real Garuda API (only WhatsApp/SMS/Email/Voice). The button is deliberately **optimistic**: the toast fires immediately, then upgrades to "Delivered" or downgrades to "Draft approved · delivery unavailable" once the call resolves — so a dead integration never produces a dead moment on stage. Confirm with whoever owns Garuda whether GChat is supported at all before this is anything but decorative.
4. **`prd_draft: Optional[str]`** — the real PRD Generator node hasn't shipped, so there's nothing to render from it yet. `core/models/prd.model.ts`'s `buildPrdView()` builds an equivalent structured PRD *from* `findings` + `suggestions` (Rev 3; both real) as the fixture-mode fallback. When `prd_draft` starts arriving as markdown, prefer rendering that directly — this becomes the Day-1 fallback path.
5. **`Suggestion` (Rev 3) has no snippet field** — only `evidence_file`/`evidence_line`. `CodeGap` (Rev 2) had `snippet`; the redesign dropped it. The Code Scout panel's "Explored" code block therefore can't come from the contract — it's fixture-only UI enrichment (`EXPLORED_ANCHORS` in `run-47.fixture.ts`, one per finding, matching the real inventory in `impl/codeScout`'s `gap1_consultation.json`/`gap2_pharmacy_checkout.json`). **On a live run this code block will be empty** until this is resolved — either add `evidence_snippet` to `Suggestion`, or accept file:line-only display. Raise with Harshit.

## Running it

```bash
npm install
npm start          # ng serve — http://localhost:4200/runs/47
```

Loads on the frozen fixture by default — no backend required, nothing to configure. Press **R** to replay the pipeline animation, **P** to open the PRD drawer, **Esc** to close it (same keys as the original HTML prototype).

### Against the real backend

The service is Mohit's, on **PR #1** (`origin/pr/1` — a pull-request ref, so it does *not* show up in `git branch -r`; fetch with `git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*'`). Run it with `uvicorn app.main:app --port 8000`; `DEMO_MODE=true` in `.env.example` needs no credentials.

The live path below is verified end-to-end against that service. Once `careloop-service` exposes it:

```bash
npm start -- --proxy-config proxy.conf.json    # proxies /v1/* to http://localhost:8000
```

then open `http://localhost:4200/runs/1?live=1` — the `?live` query param switches `RunService` from the fixture to polling `GET /v1/analysis/runs/{id}` every 1.5s until `completed`/`failed`. The run id comes from the **path**, not from `?live`'s value.

Failure handling (all verified against a mock service):

| Case | Behaviour |
|---|---|
| Network down / 5xx / timeout | Retries on the poll cadence, up to 2 consecutive failures, then gives up |
| 404 | No retry — fails immediately (`run not found (404)`) |
| Payload missing `suggestions[]` (Rev 2 backend) | No retry — `backend is on the Rev 2 contract (code_gaps, no suggestions[])` |
| Any failure | Falls back to the **whole** fixture and the `source:` chip states the reason — never a mix of live and fixture data on one screen |

> `proxy.conf.json` must use `/v1/**`, not `/v1/*`. Under http-proxy-middleware v3 a single `*` matches one path segment only, so `/v1/analysis/runs/1` fell through to the SPA fallback and returned `index.html`, which surfaced as a misleading "live unreachable".

### Build / test

```bash
npm run build       # ng build — dist/careloop-ui
npm test             # ng test (vitest)
```

## Structure

```
src/app/
  core/
    models/run-state.ts       TS mirror of contracts.py — keep field-for-field in sync
    models/prd.model.ts        builds a PrdView from findings+suggestions (prd_draft fallback)
    fixtures/run-47.fixture.ts frozen demo data, provenance documented inline
    data/voc-gloss.ts          client-side English glosses (contract gap #1 above)
    services/run.service.ts        RunState signal, fixture/live source, stage derivation, /deliver
    services/demo-playback.service.ts   the "Replay run" timer-beat animation
    services/docx-export.service.ts     PRD -> .docx via JSZip, entirely client-side
  features/
    runs-dashboard/             Screen 1
    run-detail/                 Screen 2 (+ Screen 3 nested as prd-drawer)
      components/
        pipeline-tracker/       the 4-stage tracker
        funnel/                 two independently-scaled unit groups — see the class doc
        findings-list/          finding cards; nests drilldown-trail + voc-panel under #1
        drilldown-trail/        "How the agent found it"
        voc-panel/              "Users say"
        code-scout-panel/       Rev 3: grouped by finding, Explored code block + tech/business/process suggestion cards
        prd-drawer/              Screen 3 + docx export + optimistic Approve
```

Standalone components throughout (Angular 22 default), signals for state, zoneless change detection — no `zone.js` dependency, matches this scaffold's defaults.
