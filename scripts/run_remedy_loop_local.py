"""Live Remedy Loop run: real GitLab blob search + real sphere LLM.

    LLM_MODE=sphere SPHERE_APP_TOKEN=... GITLAB_TOKEN=... \
        python scripts/run_remedy_loop_local.py

Uses the mechanism Code Scout located in timor/oms for the PD abandon finding.
Read-only throughout: GitLab search + raw-file reads only.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.code_scout.remedy_loop import run_remedy_loop
from app.integrations.sphere import SphereClient
from app.schemas.contracts import CodeGap

GITLAB = "https://gitlab.devops.mhealth.tech/api/v4"
GL_TOKEN = os.environ.get("GITLAB_TOKEN", "")
PROJECT_IDS = {"timor/oms": 61}
TEMPLATE = 21689
client = SphereClient()
searches = {"n": 0}


def search_fn(repo: str, term: str) -> list[dict]:
    """Read-only GitLab blob search, main-source files only."""
    pid = PROJECT_IDS.get(repo)
    if not pid:
        return []
    url = (f"{GITLAB}/projects/{pid}/search?scope=blobs&search="
           + urllib.parse.quote(term))
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": GL_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            hits = json.loads(r.read())
    except Exception as e:
        print(f"    search error {repo}:{term} -> {e}", flush=True)
        return []
    searches["n"] += 1
    out = []
    for h in hits:
        p = h.get("path", "")
        if "/test/" in p or not p.endswith(".java"):
            continue
        out.append({"path": p, "line": h.get("startline"),
                    "snippet": (h.get("data") or "")[:400]})
    print(f"    search {repo}:'{term}' -> {len(out)} src hits", flush=True)
    return out[:4]


def llm(ctx: dict) -> dict:
    out = client.call("code-gap-assessment", TEMPLATE,
                      {"code_context": json.dumps(ctx)})
    if ctx.get("mode") == "remedy_proposal":
        print(f"  [proposer] {len(out.get('remedies') or [])} remedies", flush=True)
    else:
        print(f"  [verifier] status={out.get('status')} "
              f"file={out.get('evidence_file')}", flush=True)
    return out


gap = CodeGap(
    finding_rank=1, origin="warehouse", stage="pharmacy_checkout",
    service="timor-oms", repo="timor/oms", mechanism_found=True,
    gap_class="missing_retention_hook",
    gap_statement=("A scheduled task abandons pharmacy orders after a timeout "
                   "(timeToAbandonOrderInMinutes); CartAbandonAdapterService runs the batch. "
                   "417,398 orders/wk are abandoned this way with no user re-engagement observed."),
    file="src/main/java/com/halodoc/timor/oms/configuration/OrderAbandonConfiguration.java",
    line=12,
    snippet="private Integer timeToAbandonOrderInMinutes;  // CartAbandonAdapterService runs the batch",
)

print(f"Running Remedy Loop live (mode={client.mode}, template {TEMPLATE})...", flush=True)
out = run_remedy_loop(llm, search_fn, gap,
                      "413,973 PD orders/wk abandoned before confirmation; "
                      "rx-gated confirm 30.0% vs 39.0% non-rx",
                      repos=["timor/oms"])

print(f"\n=== REMEDY VERDICTS ({searches['n']} searches used) ===")
for i, r in enumerate(out.remedies, 1):
    print(f"\n{i}. [{(r.status or 'unverified').upper()}] {r.proposal[:150]}")
    print(f"   signature: {r.signature[:150]}")
    if r.evidence_file:
        print(f"   evidence:  {r.evidence_file}:{r.evidence_line}")
    print(f"   searched:  {r.searched_terms[:6]}  (iterations={r.iterations})")
    if r.status is None:
        print("   UNVERIFIED — budget exhausted before any search (never ruled absent)")
