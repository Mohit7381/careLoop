"""Promote funnel-hypothesis-generation (template 21687) to v6.

WHY: v5's system message ends with

    "- Budget is limited (budget_remaining is provided): prefer concluding with
       well-evidenced findings over spending remaining budget on low-value cuts."

which is what a live run obeyed when it declared done=true after 3 of its 10
turns, having never queried stock_status — a 35.8pp conversion spread — and
settled for the 9pp rx-gated cut instead.

The exploration floor in app/agents/analyst/phase2.py already enforces the
correct behaviour deterministically, so this is about the model CHOOSING a good
order rather than being marched through one. Nothing breaks if it is not run.

    SPHERE_APP_TOKEN=... python scripts/promote_template_21687_v6.py [--dry-run]

Read-only without --apply: prints the exact diff and exits.
"""
import json
import os
import sys
import urllib.request

BASE = ("http://sphere-platform.stage-k8s.halodoc.com"
        "/v2/projects/7121/use-cases/12812/prompt-templates/21687")
TOKEN = os.environ.get("SPHERE_APP_TOKEN", "")
HEADERS = {"X-APP-TOKEN": TOKEN, "Content-Type": "application/json"}

OLD = ("- Budget is limited (budget_remaining is provided): prefer concluding with "
       "well-evidenced findings over spending remaining budget on low-value cuts.")

NEW = """- rate_bearing_dimensions are the cuts that carry `converted`. ONLY these can show one
  segment converting worse than another; every other cut can only show a distribution
  ("most abandons look like X"), never a gap. Prefer them, and query them FIRST.
- Do NOT set done=true while rate_bearing_not_yet_tried is non-empty. A cut you have not
  looked at cannot be a low-value cut — you do not yet know what is in it. The runtime
  enforces this and will query them for you, so concluding early only costs you the
  chance to choose the order.
- Budget is limited (budget_remaining is provided). Once every rate-bearing dimension has
  been tried, prefer concluding with well-evidenced findings over spending what is left on
  distribution-only cuts."""


def call(url, method="GET", payload=None):
    req = urllib.request.Request(
        url, method=method, headers=HEADERS,
        data=json.dumps(payload).encode() if payload else None)
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read())


def main() -> int:
    if not TOKEN:
        print("SPHERE_APP_TOKEN is not set"); return 1
    apply = "--apply" in sys.argv

    current = call(BASE)
    system_message = current["system_message"]
    print(f"template 21687 is at v{current['version']} (is_active={current['is_active']})")

    if NEW.splitlines()[0] in system_message:
        print("v6 wording is already live — nothing to do."); return 0
    if OLD not in system_message:
        print("ABORT: the v5 anchor line is not in the system message.")
        print("Someone has edited it since. Inspect before changing anything:")
        print(f"  curl -H 'X-APP-TOKEN: ...' {BASE}")
        return 1

    print("\n--- REMOVE " + "-" * 62)
    print(OLD)
    print("--- ADD " + "-" * 65)
    print(NEW)
    print("-" * 73)

    if not apply:
        print("\nDry run. Re-run with --apply to patch and promote.")
        return 0

    print("\nPATCH (creates a snapshot; does NOT activate it)...")
    call(BASE, "PATCH", {"system_message": system_message.replace(OLD, NEW, 1)})

    # The versions endpoint returns {"result": [...]} — not a bare list, and not
    # under "data"/"versions". Guessing that shape cost a half-applied run: the
    # PATCH had already created the snapshot when the parse blew up, leaving v6
    # authored but unpromoted.
    versions = call(f"{BASE}/versions")
    rows = versions["result"] if isinstance(versions, dict) else versions
    if not rows:
        print("ABORT: /versions returned nothing; snapshot may exist unpromoted.")
        return 1
    latest = max(int(v["version"]) for v in rows)
    print(f"  versions: {sorted(int(v['version']) for v in rows)} -> promoting {latest}")

    out = call(f"{BASE}/promote", "PATCH", {"version_id": latest})
    print(f"promoted: v{out.get('version')} is_active={out.get('is_active')}")
    print("\nVerify with a live Analyst run:")
    print("  LLM_MODE=sphere SPHERE_APP_TOKEN=... python scripts/run_analyst_local.py")
    print("Expect the model to pick rate-bearing cuts FIRST, with the floor never firing")
    print("(no 'exploration floor' text in the trail).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
