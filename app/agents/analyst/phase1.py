"""Analyst phase 1 — deterministic funnel math. No LLM anywhere in this file.

Encodes the data rules learned (and paid for) during the manual dress-rehearsal:
  - the consultation/pharmacy facts are one row per (transaction, status) —
    the Fetcher dedupes; HERE we only ever consume already-deduped stage counts
  - recorded reasons drift in casing -> normalize before clustering
  - re-creation artifacts (address change / add items) are NOT user abandonment
  - k-anonymity floor: segments with n < K are suppressed, never shown
  - pd_category values are multi-tag strings ("A,B,C;") -> FIRST tag is primary
"""
from collections import defaultdict
from typing import Optional

from app.schemas.contracts import ReasonRow, Snapshot, SnapshotRow

K_FLOOR = 25


def normalize_reason(reason: str) -> str:
    return " ".join((reason or "").strip().lower().split())


def normalize_category(raw: str) -> str:
    """Multi-tag CT category string -> primary category (first tag, trimmed)."""
    if not raw:
        return "unknown"
    first = raw.split(";")[0].split(",")[0].strip()
    return first or "unknown"


def suppress(rows: list[SnapshotRow], k: int = K_FLOOR) -> list[SnapshotRow]:
    out = []
    for r in rows:
        if r.entered < k:
            out.append(r.model_copy(update={"entered": 0, "converted": 0, "suppressed": True}))
        else:
            out.append(r)
    return out


def funnel_table(snapshot: Snapshot, stage_order: list[str]) -> list[dict]:
    """Ordered stage table with conversion-from-previous, from the 'all' segment rows."""
    by_stage = {r.stage: r for r in snapshot.stages if r.dimension == "all"}
    table, prev_count = [], None
    for stage in stage_order:
        row = by_stage.get(stage)
        if row is None:
            continue
        count = row.entered
        conv = round(count / prev_count, 4) if prev_count else None
        table.append({"stage": stage, "count": count, "conversion_from_previous": conv})
        prev_count = count
    return table


def largest_drop(table: list[dict]) -> Optional[dict]:
    """Largest ABSOLUTE loss between adjacent stages — decided before any LLM runs."""
    worst = None
    for prev, cur in zip(table, table[1:]):
        lost = prev["count"] - cur["count"]
        if worst is None or lost > worst["lost"]:
            worst = {
                "from_stage": prev["stage"], "to_stage": cur["stage"],
                "lost": lost, "share_of_prev": round(lost / prev["count"], 4) if prev["count"] else 0.0,
            }
    return worst


def cluster_reasons(reasons: list[ReasonRow], artifact_reasons: list[str]) -> dict:
    """Case-normalized reason clusters, with re-creation artifacts split out."""
    artifacts_norm = {normalize_reason(a) for a in artifact_reasons}
    user, artifact = defaultdict(int), defaultdict(int)
    for r in reasons:
        key = normalize_reason(r.cancellation_reason)
        (artifact if key in artifacts_norm else user)[key] += r.count
    user_total, artifact_total = sum(user.values()), sum(artifact.values())
    grand = user_total + artifact_total
    return {
        "user_reasons": dict(sorted(user.items(), key=lambda kv: -kv[1])),
        "artifact_reasons": dict(sorted(artifact.items(), key=lambda kv: -kv[1])),
        "user_total": user_total,
        "artifact_total": artifact_total,
        "artifact_share": round(artifact_total / grand, 4) if grand else 0.0,
    }
