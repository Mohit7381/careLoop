# CareLoop UI

Angular implementation of Screens 1–3 (Runs dashboard, Run detail, PRD draft) from the CareLoop Build Plan's design prompt. Renders `RunState` — the shared state contract in [`app/schemas/contracts.py`](../codeScout/app/schemas/contracts.py) — as the funnel, findings, drill-down trail, "Users say" panel, and Code Scout's "money moment," plus a PRD drawer with a client-side `.docx` export.

## What's implemented

- **Screen 1 — Runs dashboard** (`features/runs-dashboard`): a static past-runs table + "New analysis". Minimal on purpose — the design prompt gives it five seconds of demo time and none of the script's beats happen here.
- **Screen 2 — Run detail** (`features/run-detail`): the main screen. Pipeline tracker (4 stages) → funnel → findings (ranked, origin-badged) → drill-down trail + "Users say" nested under finding #1 → Code Scout panel.
- **Screen 3 — PRD drawer** (`features/run-detail/components/prd-drawer`): DRAFT banner, Overview/Goals/FRs/Open Questions, **Approve & send to GChat**, **Request changes**, **Download .docx**.
- **Demo playback** (`core/services/demo-playback.service.ts`): the "Replay run" animation — hard-coded timer beats, not real backend progress, so every rehearsal runs identically. Ported from the original HTML prototype.
- **`.docx` export** (`core/services/docx-export.service.ts`): builds a real OOXML `.docx` in-browser via JSZip — no backend endpoint, no round-trip.
- **contracts.py v2 alignment**: `core/models/run-state.ts` is a hand-written TypeScript mirror of `contracts.py` — same field names, same shapes (`Finding.segments` as `{dimension,value}[]`, `Finding.evidence` as `{type,metric,value}[]`, `CodeGap.mechanism_found: bool` with the `gap_class`/`no_match_reason` either-or, `RoutingStage` as an exact-match routing category, not a funnel-stage id). Do not rename anything here without syncing with Nakul/Harshit, same rule as the Python side.
- **The `mechanism_found=false` state is a real UI state**, not a TODO: `code-scout-panel.component` renders "NO MECHANISM FOUND" with the `no_match_reason` in plain words when Code Scout comes back empty — this mirrors `CodeGap.model_post_init`'s validation on the Python side.

## Fixture data — what's real vs. illustrative

`core/fixtures/run-47.fixture.ts` is `run #47`, pharmacy delivery, 2026-08-26 → 2026-09-02. Provenance is documented at the top of that file; summary:

| Section | Source |
|---|---|
| `snapshot`, `findings`, `drilldown_trail`, `voc` | The 7-day hand-run (2026-09-02), k≥25 suppression applied at fetch — matches the Build Plan's design prompt verbatim |
| `code_gaps[0]` (finding #1, `bintan/consultation`) | Copied from `impl/codeScout`'s `fixtures/code_scout/gap1_consultation.json` — a **live** GitLab search, verified 2026-09-03. This is the money moment and it's real. |
| `code_gaps[1]` (finding #2, `timor/oms`) | Copied from `gap2_pharmacy_checkout.json` — **not the same claim as gap1**. Harshit's own fixture note says `cancelOrderAndNotifyUser()` genuinely calls `notifyUsersWhatsapp`, so "no re-engagement hook exists" is *unconfirmed* for pharmacy. Kept verbatim, caveat included — the UI shows it as a secondary "+1 more code gap" note, not the primary panel, and the PRD's Open Questions carries the same caveat. **Do not present this one as settled without checking the notification template content first.** |
| `trend_report` | Illustrative/empty — no previous-window figures were published for pharmacy delivery. The Reporter node hasn't shipped, so there's no trend section in this build (`SHOW_TREND` equivalent removed entirely rather than shown empty). |

## Known contract gaps

Found while wiring the UI to `contracts.py` v2 — raise before relying on the affected feature, don't work around them silently in a second place:

1. **`VocQuote` has no `gloss` field.** The design prompt's "Users say" panel needs an English gloss under each Indonesian quote (the human moment). Kept as a client-side lookup keyed on quote text (`core/data/voc-gloss.ts`) rather than inventing a contract field unilaterally. Add `VocQuote.gloss` to `contracts.py` and this becomes dead code.
2. **`RunStatus` has no per-stage state**, only one global field: `queued | extracting | analyzing | reporting | completed | failed`. `reporting` jumps SCAN SERVICE CODE straight to `done` and nothing distinguishes PRD drafting — so **the live path can never animate the money moment**; only the fixture-mode "Replay run" can, because it fakes the timing. See the doc comment on `STATUS_MAP` in `run.service.ts`. Fix is two more enum values (`scanning`, `drafting`) plus each LangGraph node stamping its own status.
3. **`POST /v1/analysis/runs/{id}/deliver` doesn't exist.** The Approve button is wired against it (`RunService.deliver()`), but there's no backend route yet, and no verified example shows a GChat channel type in the real Garuda API (only WhatsApp/SMS/Email/Voice). The button is deliberately **optimistic**: the toast fires immediately, then upgrades to "Delivered" or downgrades to "Draft approved · delivery unavailable" once the call resolves — so a dead integration never produces a dead moment on stage. Confirm with whoever owns Garuda whether GChat is supported at all before this is anything but decorative.
4. **`prd_draft: Optional[str]`** — the real PRD Generator node hasn't shipped, so there's nothing to render from it yet. `core/models/prd.model.ts`'s `buildPrdView()` builds an equivalent structured PRD *from* `findings` + `code_gaps` (which are real) as the fixture-mode fallback. When `prd_draft` starts arriving as markdown, prefer rendering that directly — this becomes the Day-1 fallback path.

## Running it

```bash
npm install
npm start          # ng serve — http://localhost:4200/runs/47
```

Loads on the frozen fixture by default — no backend required, nothing to configure. Press **R** to replay the pipeline animation, **P** to open the PRD drawer, **Esc** to close it (same keys as the original HTML prototype).

### Against the real backend

Nothing serves `GET /v1/analysis/runs/{id}` outside `impl/codeScout`'s tests yet. Once `careloop-service` exposes it:

```bash
npm start -- --proxy-config proxy.conf.json    # proxies /v1/* to http://localhost:8000
```

then open `http://localhost:4200/runs/47?live=47` — the `?live=` query param switches `RunService` from the fixture to polling `GET /v1/analysis/runs/{id}` every 1.5s until `completed`/`failed`. A fetch failure falls back to the fixture and the `source:` chip in the sub-header says so (`live unreachable — showing fixture`) — the screen is never left mid-state.

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
    models/prd.model.ts        builds a PrdView from findings+code_gaps (prd_draft fallback)
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
        code-scout-panel/       the money moment, including mechanism_found=false
        prd-drawer/              Screen 3 + docx export + optimistic Approve
```

Standalone components throughout (Angular 22 default), signals for state, zoneless change detection — no `zone.js` dependency, matches this scaffold's defaults.
