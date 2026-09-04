"""Local end-to-end Analyst run: real sphere LLM, frozen fixtures.

    LLM_MODE=sphere SPHERE_APP_TOKEN=... python scripts/run_analyst_local.py
    LLM_MODE=replay python scripts/run_analyst_local.py          # offline, deterministic

Add RECORD_REPLAY=1 to a live run to (re)record fixtures/llm_replay/ — off by
default so an exploratory live run never clobbers the demo's frozen session.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.analyst.analyst import run_analyst
from app.integrations.sphere import SphereClient
from app.schemas.contracts import RunState, Snapshot

JOURNEY = os.environ.get("JOURNEY", "pd_checkout")
FIX = Path("fixtures") / JOURNEY
REPLAY = Path("fixtures/llm_replay") / JOURNEY / "funnel-hypothesis-generation"
IDS = json.loads(Path("fixtures/pd_checkout/sphere_ids.json").read_text())  # sphere ids are project-wide
TEMPLATE = next(u["template_id"] for u in IDS["use_cases"]
                if u["name"] == "funnel-hypothesis-generation")

client = SphereClient()
# Recording is OPT-IN: a plain live run must not silently overwrite the
# committed replay fixtures the demo depends on.
RECORD = os.environ.get("RECORD_REPLAY") == "1"
if RECORD:
    REPLAY.mkdir(parents=True, exist_ok=True)
counter = {"n": 0}

def llm(ctx: dict) -> dict:
    out = client.call("funnel-hypothesis-generation", TEMPLATE,
                      {"analysis_context": json.dumps(ctx)})
    if RECORD:
        (REPLAY / f"{counter['n']}.json").write_text(json.dumps(out, indent=1))
    counter["n"] += 1
    q = (out.get("next_question") or {})
    print(f"  [LLM turn {counter['n']}] done={out.get('done')} "
          f"next={q.get('dimension')} findings={len(out.get('findings') or [])}", flush=True)
    return out

state = RunState(
    run_id=999, journey=JOURNEY, demo_mode=True, status="analyzing",
    window_start="2026-08-27", window_end="2026-09-02",
    prev_window_start="2026-08-20", prev_window_end="2026-08-26",
    snapshot=Snapshot(**json.loads((FIX / "snapshot.json").read_text())),
)
cuts = json.loads((FIX / "cohort_cuts.json").read_text())
reviews = json.loads((FIX / "reviews_scrubbed.json").read_text())

print(f"Running Analyst live (journey={JOURNEY}, mode={client.mode}, template {TEMPLATE})...", flush=True)
out = run_analyst(state, llm=llm, cohort_cuts=cuts, reviews=reviews)

print(f"\n=== RESULT ===")
print(f"status: {out.status} | findings: {len(out.findings)} | "
      f"drill-down turns: {len(out.drilldown_trail)} | LLM calls: {counter['n']}")
for f in out.findings:
    tag = f"[{f.origin}/{f.stage}/{f.confidence}]"
    extra = f" reviews={f.review_count}" if f.origin == "voc" else \
            f" evidence={[e.value for e in f.evidence][:4]}"
    print(f"  #{f.rank} {tag}{extra}\n     {f.hypothesis[:150]}")
print("trail:", [(s.dimension, s.note) for s in out.drilldown_trail])
