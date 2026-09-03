"""Routing table: RoutingStage -> owning repo(s).

Confirmed against the real GitLab instance (gitlab.devops.mhealth.tech,
2026-09-03) - every path below resolves exactly as written:
  bintan/consultation      -> project id 311
  timor/oms                -> project id 61
  timor/fulfilment         -> project id 79
  scrooge/payment-service  -> project id 842
  transformers/garuda      -> project id 37

pharmacy_checkout has two repos. CodeGap allows multiple rows per
finding_rank (see RunState.gaps_for), but Code Scout's own policy here is:
try repos in listed order, stop at the first one that resolves a gap, and
only fall through to the next repo if the first finds nothing. This is a
Code Scout design decision, not a contract requirement - revisit if the
team wants both repos searched unconditionally.
"""
from __future__ import annotations

from app.schemas.contracts import RoutingStage

RepoInfo = dict[str, str]

ROUTING_TABLE: dict[RoutingStage, list[RepoInfo]] = {
    "consultation": [
        {"service": "consultation", "repo": "bintan/consultation"},
    ],
    "pharmacy_checkout": [
        {"service": "oms", "repo": "timor/oms"},
        {"service": "fulfilment", "repo": "timor/fulfilment"},
    ],
    "payments": [
        {"service": "payment-service", "repo": "scrooge/payment-service"},
    ],
    "re_engagement": [
        {"service": "garuda", "repo": "transformers/garuda"},
    ],
}


def repos_for_stage(stage: RoutingStage) -> list[RepoInfo]:
    return ROUTING_TABLE[stage]
