"""The `code-gap-assessment` sphere-platform use case.

Per the build table, this is Harshit's to build (row 3: "Code Scout -
Routing table, GitLab search tools, code-gap use case"), not Mohit's -
his row covers trend-narrative and prd-generation only.

StubCodeGapAssessor is the Day-1 stand-in: rule-based against the known
fixtures, so the pipeline can run end-to-end before sphere-platform is
wired up. SpherePlatformCodeGapAssessor is the real LLM-backed
implementation, wired into app/pipeline/nodes/code_scout.py for
demo_mode=False - same interface, no change needed in node.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol
from urllib.error import URLError

from app.agents.code_scout.errors import CodeScoutExternalError
from app.config import get_settings
from app.integrations.sphere import SphereClient
from app.schemas.contracts import Finding, GapClass, _GAP_CLASSES

SPHERE_IDS_PATH = Path("fixtures/pd_checkout/sphere_ids.json")
SPHERE_USE_CASE = "code-gap-assessment"


_CLASS_HINTS = {
    "missing_retention_hook": ("retention", "hook", "notif", "communicat", "reengag", "re_engag",
                               "nudge", "remind", "outreach", "message"),
    "ux_gap":                 ("ux", "ui", "client", "screen", "user_facing", "experience", "frontend"),
    "logic_flaw":             ("logic", "bug", "flaw", "incorrect", "wrong", "race", "timeout_too"),
}


def normalise_gap_class(raw) -> tuple[str, bool]:
    """Map whatever the model called the gap onto the closed set.

    Returns (gap_class, exact). The model was seen inventing classes like
    'configuration-only-no-usage-evidence' and 'missing_consultation_event_types'
    on every single live call; rejecting those threw away a mechanism that had
    just been located at a real file:line. An obvious synonym is mapped; anything
    else becomes "unclassified" and the raw text is kept on the gap statement so
    a reviewer sees what the model actually said.
    """
    key = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in _GAP_CLASSES:
        return key, True
    for cls, needles in _CLASS_HINTS.items():
        if any(n in key for n in needles):
            return cls, False
    return "unclassified", False


def bracket_safe(text: str) -> str:
    """Sphere rejects any model output containing HTML-looking tags, and a Java
    snippet is full of List<Order> generics the model will echo verbatim. Two
    live assess() calls died exactly that way. Swap the brackets on the way in
    so there is nothing to echo."""
    return (text or "").replace("<", "‹").replace(">", "›")


@dataclass
class GapAssessment:
    gap_class: GapClass
    gap_statement: str
    proposed_change_location: Optional[str] = None


class CodeGapAssessor(Protocol):
    def propose_search_terms(self, finding: Finding) -> list[str]: ...

    def assess(self, finding: Finding, file: str, snippet: str) -> GapAssessment: ...


class StubCodeGapAssessor:
    """Day-1 rule-based stand-in - NOT the real LLM call.

    assess() below is hand-written against the two real candidates found via
    live GitLab search on 2026-09-03. GAP 1 (ConsultationDao) is fully
    hand-verified per the plan. GAP 2 (BaseCancellationTypeAdapterService) was
    CORRECTED 2026-09-03 (Harshit, PR #3): the original candidate
    (cancelOrderAndNotifyUser:208) was a sibling method never actually called
    by the timer job. The real mechanism is abandonOrderV2:298 — the method
    the timer-driven AbandonOrderService actually calls — confirmed via full
    call-chain trace + grep to call zero notification methods. Now a clean,
    fully confirmed gap like GAP 1, not a weaker candidate.
    """

    def propose_search_terms(self, finding: Finding) -> list[str]:
        if finding.journey_events:
            # Real analytics event names (Analyst, decision #11) - better
            # search seed material than parsing hypothesis prose.
            return finding.journey_events
        if finding.origin == "voc" and finding.theme_search_terms:
            return finding.theme_search_terms
        # Crude Day-1 fallback - the real LLM call replaces this entirely.
        words = [w.strip(",.") for w in finding.hypothesis.split() if len(w) > 4]
        return words[:5] or [finding.hypothesis]

    def assess(self, finding: Finding, file: str, snippet: str) -> GapAssessment:
        if "ConsultationDao" in file:
            return GapAssessment(
                gap_class="missing_retention_hook",
                gap_statement=(
                    "The abandon script has no re-engagement hook; Garuda is "
                    "never called before the kill."
                ),
                proposed_change_location=f"{file}: call Garuda before the abandon kill executes",
            )
        if "CancellationTypeAdapterService" in file:
            return GapAssessment(
                gap_class="missing_retention_hook",
                gap_statement=(
                    "abandonOrderV2 — the method the timer-driven abandon job actually calls — "
                    "reverses benefits/payment-links/delivery-fee and marks the order failed, but "
                    "calls zero notification/communication methods anywhere in its body. Garuda is "
                    "never called before the kill; sendCommunication exists in this same file but "
                    "82 lines away, in an unrelated method never reached by this path."
                ),
                proposed_change_location=f"{file}: call Garuda before abandonOrderV2 marks the order failed",
            )
        return GapAssessment(
            gap_class="ux_gap",
            gap_statement=(
                f"Mechanism located in {file}, but classification wasn't "
                "hand-verified - treat as a placeholder pending the real LLM call."
            ),
        )


class SpherePlatformCodeGapAssessor:
    """Real LLM-backed CodeGapAssessor. Same interface as StubCodeGapAssessor
    - node.py needs zero changes; only app/pipeline/nodes/code_scout.py's
    caller picks one or the other (demo_mode).

    Uses app.integrations.sphere.SphereClient - the same client already
    wired into the real Analyst node (app/pipeline/nodes/analyst.py) and
    scripts/run_remedy_loop_local.py - rather than a separate hand-rolled
    HTTP client, so this shares whatever they've already confirmed live
    rather than re-guessing the endpoint contract.

    Calling convention (confirmed live, scripts/run_remedy_loop_local.py):
    the whole call context goes in as ONE JSON-string-valued param under
    "code_context" - this template's own prompt reads that single variable,
    not individually-named ones (contrast with analyst.py's _sphere_llm(),
    which flattens ctx's top-level keys as separate params - a different
    template, different convention).

    ASSUMPTION NOT YET CONFIRMED: this reuses the code-gap-assessment
    template's `mode` discriminator (confirmed for "remedy_proposal" /
    "remedy_verification" in remedy_loop.py) for two NEW mode values,
    "propose_search_terms" and "assess_gap" - reasonable given the template
    already branches on `mode`, but nobody has run these two live yet.
    """

    def __init__(self, service_type: Optional[str] = None):
        ids = json.loads(SPHERE_IDS_PATH.read_text())
        self._template_id = next(
            u["template_id"] for u in ids["use_cases"] if u["name"] == SPHERE_USE_CASE
        )
        settings = get_settings()
        self._client = SphereClient(mode="sphere", service_type=service_type or settings.sphere_platform_service_type)

    def _call(self, ctx: dict) -> dict:
        try:
            return self._client.call(SPHERE_USE_CASE, self._template_id, {"code_context": json.dumps(ctx)})
        except URLError as exc:
            raise CodeScoutExternalError(f"Sphere Platform call failed (mode={ctx.get('mode')!r}): {exc}") from exc
        except RuntimeError as exc:
            # SphereClient._live() raises RuntimeError itself when status != "SUCCESS".
            raise CodeScoutExternalError(f"Sphere Platform call did not succeed (mode={ctx.get('mode')!r}): {exc}") from exc
        except ValueError as exc:
            raise CodeScoutExternalError(
                f"Sphere Platform returned invalid JSON (mode={ctx.get('mode')!r}): {exc}"
            ) from exc

    def propose_search_terms(self, finding: Finding) -> list[str]:
        if finding.journey_events:
            return finding.journey_events
        if finding.origin == "voc" and finding.theme_search_terms:
            return finding.theme_search_terms
        data = self._call({"mode": "propose_search_terms", "hypothesis": finding.hypothesis, "stage": finding.stage})
        try:
            return data["search_terms"]
        except (KeyError, TypeError) as exc:
            raise CodeScoutExternalError(f"Sphere response missing search_terms: {exc}") from exc

    def assess(self, finding: Finding, file: str, snippet: str) -> GapAssessment:
        data = self._call({
            "mode": "assess_gap",
            "hypothesis": finding.hypothesis,
            "file": file,
            "snippet": bracket_safe(snippet),
            "allowed_gap_classes": sorted(c for c in _GAP_CLASSES if c != "unclassified"),
            "rules": ["gap_class MUST be one of allowed_gap_classes, verbatim.",
                      "Never emit angle-bracket characters (the less-than or greater-than signs) anywhere in the output."],
        })
        raw = data.get("gap_class")
        gap_class, exact = normalise_gap_class(raw)
        statement = data.get("gap_statement") or f"Mechanism located in {file}."
        if not exact:
            statement += f" [model class: {raw!r}, recorded as {gap_class}]"
        return GapAssessment(
            gap_class=gap_class,
            gap_statement=statement,
            proposed_change_location=data.get("proposed_change_location"),
        )
