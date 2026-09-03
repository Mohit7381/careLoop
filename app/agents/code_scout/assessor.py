"""The `code-gap-assessment` sphere-platform use case.

Per the build table, this is Harshit's to build (row 3: "Code Scout -
Routing table, GitLab search tools, code-gap use case"), not Mohit's -
his row covers trend-narrative and prd-generation only.

StubCodeGapAssessor is the Day-1 stand-in: rule-based against the known
fixtures, so the pipeline can run end-to-end before sphere-platform is
wired up. Swap in a real SpherePlatformCodeGapAssessor once the shared
`funnel-analysis` project (Nakul's to provision) is up - same interface,
no change needed in node.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from app.schemas.contracts import Finding, GapClass


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
