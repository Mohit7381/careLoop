"""Routing table: routing category -> owning repo(s).

Per contracts v3 (Appendix A #2), the routing category vocabulary is no
longer a hardcoded Literal — it comes from the active journey's
`config/journeys/{journey}.yaml` `routing:` section, keyed exactly by the
category strings Analyst assigns to Finding.stage / CodeGap.stage. This
replaces the original hardcoded 4-category ROUTING_TABLE (which was
confirmed against real GitLab project ids on 2026-09-03 — see below,
those ids are worth re-verifying if pd_checkout.yaml's repo list ever
drifts from them):
  bintan/consultation      -> project id 311
  timor/oms                -> project id 61
  timor/fulfilment         -> project id 79
  scrooge/payment-service  -> project id 842
  transformers/garuda      -> project id 37

Multiple repos per category: try in listed order, stop at the first repo
that resolves a gap (Code Scout's own policy, not a contract requirement).
"""
from __future__ import annotations

from app.journeys import load_journey

RepoInfo = dict[str, str]


def _service_name(repo: str) -> str:
    return repo.split("/")[-1]


def repos_for_stage(stage: str, journey: str = "pd_checkout") -> list[RepoInfo]:
    routing = load_journey(journey)["routing"]
    if stage not in routing:
        raise KeyError(f"'{stage}' is not a routing category in journey '{journey}'")
    return [{"service": _service_name(repo), "repo": repo} for repo in routing[stage]]
