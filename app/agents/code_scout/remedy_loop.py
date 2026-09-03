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
from typing import Any, Callable

from app.schemas.contracts import CodeGap, Remedy

MAX_REMEDIES = 3
MAX_ITERATIONS = 2      # initial verify + one refinement
SEARCH_BUDGET = 10      # total searches across all remedies

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
        if r.get("proposal") and r.get("signature"):
            remedies.append(Remedy(
                proposal=r["proposal"], signature=r["signature"],
                search_terms=[t for t in (r.get("search_terms") or []) if t][:5],
            ))
    return remedies


def verify_remedy(llm: LLMCall, search_fn: SearchFn, remedy: Remedy,
                  repos: list[str], budget_left: int) -> tuple[Remedy, int]:
    """The proposer<->verifier loop for ONE remedy. Returns (remedy, budget_left)."""
    terms = list(remedy.search_terms)
    for iteration in range(MAX_ITERATIONS):
        hits: list[dict] = []
        for term in terms:
            if budget_left <= 0:
                break
            for repo in repos:
                if budget_left <= 0:
                    break
                found = search_fn(repo, term)
                budget_left -= 1
                remedy.searched_terms.append(f"{repo}:{term}")
                hits.extend({"repo": repo, **h} for h in (found or []))
        remedy.iterations = iteration + 1

        verdict = llm({
            "mode": "remedy_verification",
            "remedy": {"proposal": remedy.proposal, "signature": remedy.signature},
            "search_hits": hits[:10],
            "budget_left": budget_left,
        })
        status = verdict.get("status")
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
            refined = [t for t in (verdict.get("refined_search_terms") or []) if t][:5]
            if refined and iteration + 1 < MAX_ITERATIONS and budget_left > 0:
                terms = refined          # verifier unsure -> one more look
                continue
            remedy.status = "absent"
            return remedy, budget_left
        else:                            # malformed verdict -> conservative
            remedy.status = "partial"
            return remedy, budget_left
    if remedy.status is None:
        remedy.status = "absent" if budget_left > 0 else "partial"
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
