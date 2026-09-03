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
    hand-verified per the plan. GAP 2 (BaseCancellationTypeAdapterService) is
    a real, weaker candidate - communication does fire on abandonment, so the
    actual gap (if any) is about notification intent, not an outright missing
    hook. Flag that distinction before using it in the live demo; don't
    upgrade its confidence just because the stub found a file.
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
                    "A communication does fire on system abandonment "
                    "(sendCommunication / notifyUsersWhatsapp), but it reads as a "
                    "generic cancellation notice, not a cart-recovery nudge - needs "
                    "confirming against the actual template content before the PRD "
                    "claims this as a clean missing-hook gap."
                ),
                proposed_change_location=f"{file}: review the notification template used here",
            )
        return GapAssessment(
            gap_class="ux_gap",
            gap_statement=(
                f"Mechanism located in {file}, but classification wasn't "
                "hand-verified - treat as a placeholder pending the real LLM call."
            ),
        )
