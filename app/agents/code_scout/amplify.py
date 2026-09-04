"""Feature amplification — explore_shipped_feature mode (2026-09-04).

The closed-loop impact feature (app.agents.code_scout.impact) already
auto-detects every recently shipped fix and, once Reporter attaches a
metric, which of them moved a real number. This module is the other half:
of those, the ones that moved FAVOURABLY (pct_change > 0 — the only
"positive feedback" signal this pipeline can honestly measure today; it is
a real metric movement, not a text-sentiment read of reviews, which the VoC
pipeline does not classify for positive sentiment) get explored further for
ideas that build forward on a proven win, via the code-gap-assessment
use case's `explore_shipped_feature` mode.

Never proposes reverting/re-verifying a shipped feature — only extending
one that already worked. Same evidence discipline as propose_suggestions:
grounded in the shipped_fix's own snippet, one call per candidate, and a
failed or malformed call drops that candidate rather than the whole run.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.schemas.contracts import ShippedFix, Suggestion, SuggestionType

logger = logging.getLogger(__name__)

AMPLIFICATION_BUDGET = 3
LLMCall = Callable[[dict[str, Any]], dict[str, Any]]

_VALID_TYPES = {"tech", "business", "process"}


def _service_name(repo: str) -> str:
    return repo.split("/")[-1]


def _parse_amplification(item: dict, sf: ShippedFix) -> Optional[Suggestion]:
    suggestion_type: Optional[SuggestionType] = item.get("suggestion_type")
    title, description, rationale = item.get("title"), item.get("description"), item.get("rationale")
    if suggestion_type not in _VALID_TYPES or not title or not description or not rationale:
        return None
    try:
        return Suggestion(
            finding_rank=sf.finding_rank,
            origin=sf.origin,
            stage=sf.stage,
            service=_service_name(sf.repo),
            repo=sf.repo,
            suggestion_type=suggestion_type,
            title=title,
            description=description,
            rationale=rationale,
            # Verification is a separate deterministic step this pass doesn't
            # run (mirrors propose_suggestions' own contract): a tech idea
            # says something to check, not a confirmed present/absent claim.
            verification_status="unverified" if suggestion_type == "tech" else "not_applicable",
        )
    except ValueError as exc:
        logger.warning("dropping malformed explore_shipped_feature suggestion for finding #%s: %s",
                       sf.finding_rank, exc)
        return None


def propose_feature_amplifications(
    llm: Optional[LLMCall], shipped_fixes: list[ShippedFix], budget: int = AMPLIFICATION_BUDGET,
) -> list[Suggestion]:
    if llm is None:
        return []
    candidates = [sf for sf in shipped_fixes if sf.pct_change is not None and sf.pct_change > 0][:budget]
    if not candidates:
        return []

    out: list[Suggestion] = []
    for sf in candidates:
        try:
            result = llm({
                "mode": "explore_shipped_feature",
                "shipped_fix": {
                    "stage": sf.stage, "repo": sf.repo, "remedy_proposal": sf.remedy_proposal,
                    "evidence_file": sf.evidence_file, "evidence_line": sf.evidence_line,
                    "evidence_snippet": sf.evidence_snippet,
                    "commit_sha": sf.commit.short_sha, "commit_date": sf.commit.date,
                    "metric_name": sf.metric_name, "metric_unit": sf.metric_unit,
                    "previous_value": sf.previous_value, "current_value": sf.current_value,
                    "pct_change": sf.pct_change,
                },
                "rules": [
                    "Every number must come from shipped_fix. Do not compute new totals.",
                    "Describe the metric's movement as correlated with the shipped commit, "
                    "never as its proven cause.",
                    "Do not propose reverting, removing or re-verifying the shipped feature itself.",
                    "No angle brackets anywhere in the output.",
                ],
            })
        except Exception as exc:  # noqa: BLE001 — one bad call must not sink the others
            logger.warning("explore_shipped_feature failed for finding #%s (%s): %s",
                           sf.finding_rank, sf.repo, exc)
            continue
        for item in (result or {}).get("suggestions") or []:
            suggestion = _parse_amplification(item, sf)
            if suggestion is not None:
                out.append(suggestion)
    return out
