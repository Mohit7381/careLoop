"""The Remedy Loop — Code Scout phases 2-3 (proposer <-> verifier).

After the mechanism is LOCATED, a proposer LLM turn suggests up to
MAX_REMEDIES candidate improvements, each with a code-verifiable signature.
For each remedy the loop then alternates:

    verifier search (injected search_fn over the owning repos)
      -> LLM verdict: exists | absent | partial
      -> on partial/ambiguous, ONE refinement iteration with new terms

Budgets are hard: MAX_REMEDIES proposals, MAX_ITERATIONS verify rounds per
remedy, SEARCH_BUDGET total searches. The loop only READS — evidence is
file:line, never a diff. A remedy verified ABSENT feeds the PRD as a
confirmed-missing fix; one that EXISTS is surfaced so the PRD never proposes
what's already built.

Both LLM roles run on the same sphere use case (`code-gap-assessment`,
template 21689) via its `mode` field: "remedy_proposal" | "remedy_verification".
Injected callables keep this testable without network:
    llm(ctx: dict) -> dict          # parsed strict-schema model output
    search_fn(repo, term) -> list[dict{path, line, snippet}]
"""
from typing import Any, Callable, Optional

from app.schemas.contracts import CodeGap, Remedy

MAX_REMEDIES = 3
_BAD_SIGNATURES = {"", "null", "none", "n/a", "-"}

# The LLM output schema cannot express a nullable enum (gpt-5-mini strict mode),
# so the model sometimes invents descriptive statuses ("signature_not_found").
# Normalise defensively rather than collapsing everything to "partial".
_STATUS_ALIASES = {
    "exists": "exists", "found": "exists", "present": "exists",
    "code_found": "exists", "evidence_found": "exists",
    "absent": "absent", "missing": "absent", "not_found": "absent",
    "signature_not_found": "absent", "no_matching_code_found": "absent",
    "no_match": "absent", "no_results": "absent", "not_present": "absent",
    "partial": "partial", "partial_evidence_found": "partial",
    "partially_present": "partial", "related_found": "partial",
    "ambiguous": "partial", "inconclusive": "partial",
}


def normalise_status(raw: Any) -> Optional[str]:
    """Map a model-supplied status onto exists|absent|partial, or None."""
    if not raw:
        return None
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if key in _STATUS_ALIASES:
        return _STATUS_ALIASES[key]
    if "partial" in key or "ambigu" in key or "related" in key:
        return "partial"
    if "not" in key or "absent" in key or "missing" in key or "no_" in key:
        return "absent"
    if "exist" in key or "found" in key or "present" in key:
        return "exists"
    return None
MAX_ITERATIONS = 2      # initial verify + one refinement
SEARCH_BUDGET = 12      # total searches across all remedies
PER_REMEDY_SHARE = 4    # max searches one remedy may consume — stops the first
                        # remedy exhausting the budget and leaving the rest unverified

LLMCall = Callable[[dict[str, Any]], dict[str, Any]]
SearchFn = Callable[[str, str], list[dict[str, Any]]]


def propose_remedies(llm: LLMCall, gap: CodeGap, finding_summary: str) -> list[Remedy]:
    out = llm({
        "mode": "remedy_proposal",
        "finding": finding_summary,
        "mechanism": {"gap_statement": gap.gap_statement, "file": gap.file,
                      "line": gap.line, "snippet": gap.snippet,
                      "gap_class": gap.gap_class},
    })
    remedies = []
    for r in (out.get("remedies") or [])[:MAX_REMEDIES]:
        sig = str(r.get("signature") or "").strip()
        # A remedy with no real signature is not code-verifiable — the loop
        # cannot rule on it, so it never enters the pipeline (process/business
        # suggestions belong to the PRD step, unverified and labelled as such).
        if r.get("proposal") and sig.lower() not in _BAD_SIGNATURES:
            remedies.append(Remedy(
                proposal=r["proposal"], signature=sig,
                search_terms=[t for t in (r.get("search_terms") or []) if t][:5],
            ))
    return remedies


def verify_remedy(llm: LLMCall, search_fn: SearchFn, remedy: Remedy,
                  repos: list[str], budget_left: int) -> tuple[Remedy, int]:
    """The proposer<->verifier loop for ONE remedy. Returns (remedy, budget_left).

    A remedy we could not search is left UNVERIFIED (status None) — never
    ruled "absent". No hits because we did not look is not evidence of
    absence, and the pipeline's rule is that verdicts are search-backed or
    they do not ship.
    """
    if budget_left <= 0:
        return remedy, budget_left          # status stays None → unverified
    spent_here = 0
    terms = list(remedy.search_terms)
    for iteration in range(MAX_ITERATIONS):
        hits: list[dict] = []
        for term in terms:
            if budget_left <= 0 or spent_here >= PER_REMEDY_SHARE:
                break
            for repo in repos:
                if budget_left <= 0 or spent_here >= PER_REMEDY_SHARE:
                    break
                # GitLab blob search treats the query literally, so a
                # multi-word term matches nothing — search its longest token.
                q = max(term.split(), key=len) if " " in term else term
                found = search_fn(repo, q)
                budget_left -= 1
                spent_here += 1
                remedy.searched_terms.append(f"{repo}:{q}")
                hits.extend({"repo": repo, **h} for h in (found or []))
        remedy.iterations = iteration + 1

        verdict = llm({
            "mode": "remedy_verification",
            "remedy": {"proposal": remedy.proposal, "signature": remedy.signature},
            "search_hits": hits[:10],
            "budget_left": budget_left,
        })
        status = normalise_status(verdict.get("status"))
        if status in ("exists", "partial"):
            remedy.status = status
            remedy.evidence_file = verdict.get("evidence_file")
            remedy.evidence_line = verdict.get("evidence_line")
            remedy.evidence_snippet = (verdict.get("evidence_snippet") or "")[:800] or None
            if status == "exists" or iteration + 1 >= MAX_ITERATIONS:
                return remedy, budget_left
            # partial -> allow ONE refinement round with new terms
            terms = [t for t in (verdict.get("refined_search_terms") or []) if t][:5]
            if not terms:
                return remedy, budget_left
        elif status == "absent":
            # A verdict never DOWNGRADES: if a previous round already found
            # related machinery, the sharper follow-up search failing to find
            # the exact remedy does not erase that evidence — the honest
            # verdict stays "partial" (related machinery exists, remedy does
            # not). Only a remedy that was never partial can end up absent.
            if remedy.status == "partial":
                return remedy, budget_left
            refined = [t for t in (verdict.get("refined_search_terms") or []) if t][:5]
            if refined and iteration + 1 < MAX_ITERATIONS and budget_left > 0:
                terms = refined          # verifier unsure -> one more look
                continue
            remedy.status = "absent"
            return remedy, budget_left
        else:                            # malformed verdict -> conservative
            remedy.status = remedy.status or "partial"
            return remedy, budget_left
    # Loop ended without a verdict: only claim "absent" if we actually looked.
    if remedy.status is None and remedy.searched_terms:
        remedy.status = "absent"
    return remedy, budget_left


def run_remedy_loop(llm: LLMCall, search_fn: SearchFn, gap: CodeGap,
                    finding_summary: str, repos: list[str]) -> CodeGap:
    """Entry point: mutates and returns gap with verified remedies[]."""
    if not gap.mechanism_found:
        return gap                        # nothing to remedy against
    remedies = propose_remedies(llm, gap, finding_summary)
    budget = SEARCH_BUDGET
    verified = []
    for r in remedies:
        r, budget = verify_remedy(llm, search_fn, r, repos, budget)
        verified.append(r)
    gap.remedies = verified
    return gap
