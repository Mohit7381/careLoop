"""The Remedy Loop — proposer<->verifier iteration, budgets, honest verdicts."""
from app.agents.code_scout.remedy_loop import (
    MAX_ITERATIONS, SEARCH_BUDGET, run_remedy_loop)
from app.schemas.contracts import CodeGap

GAP = CodeGap(
    finding_rank=1, origin="warehouse", stage="pharmacy_checkout",
    service="timor-oms", repo="timor/oms", mechanism_found=True,
    gap_class="missing_retention_hook",
    gap_statement="Orders abandoned on a timer with no re-engagement before the kill",
    file="src/.../OrderAbandonConfiguration.java", line=12,
)
REPOS = ["timor/oms"]


def scripted_llm(script):
    calls = iter(script)
    return lambda ctx: next(calls)


def test_absent_and_exists_verdicts():
    llm = scripted_llm([
        {"remedies": [
            {"proposal": "Send a resume-checkout nudge before the abandon batch",
             "signature": "a notification/Garuda call in the abandon path",
             "search_terms": ["garuda", "notification"]},
            {"proposal": "Expose an internal un-abandon endpoint",
             "signature": "an internal resource reversing abandonment",
             "search_terms": ["InternalAbandonOrderResource"]},
        ]},
        {"status": "absent", "refined_search_terms": []},           # remedy 1
        {"status": "exists", "evidence_file": "src/.../InternalAbandonOrderResource.java",
         "evidence_line": 40, "evidence_snippet": "@Path(...)"},    # remedy 2
    ])
    hits = {"garuda": [], "notification": [],
            "InternalAbandonOrderResource": [{"path": "src/.../InternalAbandonOrderResource.java", "line": 40}]}
    gap = run_remedy_loop(llm, lambda repo, t: hits.get(t, []), GAP.model_copy(deep=True),
                          "413,973 orders/wk abandoned on a timer", REPOS)
    assert [r.status for r in gap.remedies] == ["absent", "exists"]
    assert gap.remedies[1].evidence_file.endswith("InternalAbandonOrderResource.java")
    assert gap.remedies[0].searched_terms  # audit trail kept even for absent


def test_partial_triggers_exactly_one_refinement_loop():
    llm = scripted_llm([
        {"remedies": [{"proposal": "p", "signature": "s", "search_terms": ["a"]}]},
        {"status": "partial", "evidence_file": "f.java", "evidence_line": 1,
         "refined_search_terms": ["better_term"]},                  # round 1 -> refine
        {"status": "exists", "evidence_file": "f.java", "evidence_line": 2,
         "evidence_snippet": "x"},                                  # round 2 -> settled
    ])
    seen = []
    gap = run_remedy_loop(llm, lambda repo, t: seen.append(t) or [], GAP.model_copy(deep=True), "f", REPOS)
    r = gap.remedies[0]
    assert r.status == "exists" and r.iterations == MAX_ITERATIONS
    assert "better_term" in seen                                    # the loop actually refined


def test_search_budget_is_hard():
    llm_script = [{"remedies": [
        {"proposal": f"p{i}", "signature": f"s{i}",
         "search_terms": ["t1", "t2", "t3", "t4", "t5"]} for i in range(3)]}]
    llm_script += [{"status": "absent", "refined_search_terms": []}] * 3
    calls = {"n": 0}
    def counting_search(repo, term):
        calls["n"] += 1
        return []
    gap = run_remedy_loop(scripted_llm(llm_script), counting_search,
                          GAP.model_copy(deep=True), "f", REPOS)
    assert calls["n"] <= SEARCH_BUDGET
    assert all(r.status is not None for r in gap.remedies)          # verdicts despite budget


def test_no_mechanism_means_no_remedies():
    gap = CodeGap(finding_rank=1, origin="voc", stage="payments", service="s",
                  repo="r", mechanism_found=False, no_match_reason="no_results",
                  gap_statement="nothing located")
    out = run_remedy_loop(lambda ctx: (_ for _ in ()).throw(AssertionError("LLM must not be called")),
                          lambda repo, t: [], gap, "f", REPOS)
    assert out.remedies == []


def test_status_aliases_are_normalised():
    """gpt-5-mini invents descriptive statuses because strict mode cannot
    express a nullable enum — they must not all collapse to 'partial'."""
    from app.agents.code_scout.remedy_loop import normalise_status
    assert normalise_status("signature_not_found") == "absent"
    assert normalise_status("no_matching_code_found") == "absent"
    assert normalise_status("partial_evidence_found") == "partial"
    assert normalise_status("EXISTS") == "exists"
    assert normalise_status("Related found") == "partial"
    assert normalise_status(None) is None


def test_remedies_without_a_real_signature_are_dropped():
    """Business/process suggestions aren't code-verifiable — the loop can't
    rule on them, so they never enter the pipeline."""
    from app.agents.code_scout.remedy_loop import propose_remedies
    llm = lambda ctx: {"remedies": [
        {"proposal": "verifiable", "signature": "a Garuda call in the abandon path",
         "search_terms": ["sendCommunication"]},
        {"proposal": "process change: pharmacist callback", "signature": "null",
         "search_terms": []},
        {"proposal": "another process one", "signature": "", "search_terms": []},
    ]}
    out = propose_remedies(llm, GAP, "finding")
    assert [r.proposal for r in out] == ["verifiable"]


def test_unsearched_remedy_is_unverified_not_absent():
    """No hits because we never looked is NOT evidence of absence."""
    from app.agents.code_scout.remedy_loop import verify_remedy
    from app.schemas.contracts import Remedy
    r = Remedy(proposal="p", signature="s", search_terms=["t"])
    out, left = verify_remedy(lambda ctx: {"status": "absent"},
                              lambda repo, t: [], r, ["timor/oms"], budget_left=0)
    assert out.status is None and out.searched_terms == []


def test_one_remedy_cannot_eat_the_whole_budget():
    from app.agents.code_scout.remedy_loop import PER_REMEDY_SHARE, run_remedy_loop
    llm_script = [{"remedies": [
        {"proposal": f"p{i}", "signature": f"sig{i}",
         "search_terms": ["a", "b", "c", "d", "e", "f"]} for i in range(3)]}]
    llm_script += [{"status": "absent", "refined_search_terms": []}] * 6
    calls = iter(llm_script)
    counts = {"n": 0}
    def counting(repo, t):
        counts["n"] += 1
        return []
    gap = run_remedy_loop(lambda ctx: next(calls), counting,
                          GAP.model_copy(deep=True), "f", ["timor/oms"])
    # every remedy got searched, and none exceeded its share
    assert all(r.searched_terms for r in gap.remedies)
    assert all(len(r.searched_terms) <= PER_REMEDY_SHARE for r in gap.remedies)
    assert all(r.status == "absent" for r in gap.remedies)


def test_multiword_terms_search_their_longest_token():
    from app.agents.code_scout.remedy_loop import verify_remedy
    from app.schemas.contracts import Remedy
    seen = []
    r = Remedy(proposal="p", signature="s",
               search_terms=["CartAbandonAdapterService communicationService send"])
    verify_remedy(lambda ctx: {"status": "absent"},
                  lambda repo, t: seen.append(t) or [], r, ["timor/oms"], budget_left=5)
    assert seen == ["CartAbandonAdapterService"]  # longest token, not the phrase


def test_partial_is_never_downgraded_to_absent():
    """Round 1 finds related machinery; the sharper round-2 search finds
    nothing more. The evidence already found must survive."""
    from app.agents.code_scout.remedy_loop import verify_remedy
    from app.schemas.contracts import Remedy
    llm = iter([
        {"status": "partial", "evidence_file": "ReminderServiceConfiguration.java",
         "evidence_line": 1, "refined_search_terms": ["sendOrderAbandonReminder"]},
        {"status": "absent", "refined_search_terms": []},
    ])
    r = Remedy(proposal="p", signature="s", search_terms=["reminder"])
    out, _ = verify_remedy(lambda ctx: next(llm), lambda repo, t: [],
                           r, ["timor/oms"], budget_left=8)
    assert out.status == "partial"
    assert out.evidence_file == "ReminderServiceConfiguration.java"


def test_malformed_verdict_leaves_the_remedy_unverified():
    """A response we could not parse is not evidence of anything.

    The loop used to fall back to `status = status or "partial"`, which put a
    PARTIAL claim with no file behind it into the PRD. Contracts now reject
    that shape outright, so the honest outcome is UNVERIFIED.
    """
    llm = scripted_llm([
        {"remedies": [{"proposal": "Send a nudge before the abandon batch",
                       "signature": "a Garuda call in the abandon path",
                       "search_terms": ["garuda"]}]},
        {"status": "🤷 no idea", "refined_search_terms": []},
    ])
    gap = run_remedy_loop(llm, lambda repo, t: [], GAP.model_copy(deep=True),
                          "summary", REPOS)
    assert gap.remedies[0].status is None
    assert gap.remedies[0].searched_terms  # we did look; we just got no verdict


def test_exists_without_a_named_file_is_not_accepted():
    """"It's already there" with nothing to point at is an assertion, not
    evidence — and Remedy's validator would reject the object anyway."""
    llm = scripted_llm([
        {"remedies": [{"proposal": "Reuse the existing communication hook",
                       "signature": "sendCommunication in the abandon path",
                       "search_terms": ["sendCommunication"]}]},
        {"status": "exists", "evidence_file": None, "refined_search_terms": []},
        {"status": "exists", "evidence_file": None, "refined_search_terms": []},
    ])
    hits = {"sendCommunication": [{"path": "src/.../Base.java", "line": 216}]}
    gap = run_remedy_loop(llm, lambda repo, t: hits.get(t, []),
                          GAP.model_copy(deep=True), "summary", REPOS)
    assert gap.remedies[0].status is None
    assert gap.remedies[0].evidence_file is None


def test_unrecognised_statuses_do_not_get_guessed_into_a_verdict():
    """Substring matching used to turn prose into confidence: 'no idea' hit
    the `no_` branch and became ABSENT, and any status containing
    'notification' hit the `not` branch. Unknown means unverified."""
    from app.agents.code_scout.remedy_loop import normalise_status

    for unknown in ("no idea", "notification pending", "maybe someday", "42", ""):
        assert normalise_status(unknown) is None, unknown

    # The invented-but-meaningful values the model really does emit still map.
    assert normalise_status("signature_not_found") == "absent"
    assert normalise_status("no_matching_code_found") == "absent"
    assert normalise_status("partial_evidence_found") == "partial"
    assert normalise_status("code_found") == "exists"


def test_negation_beats_the_word_it_negates():
    """Token matching alone read "no_notification_found" as EXISTS, because
    "found" is in the token set — the worst direction to be wrong in, and a
    very plausible thing for the verifier to say when the search was for a
    notification call in an abandon path."""
    from app.agents.code_scout.remedy_loop import normalise_status

    for negated in ("no_notification_found", "not_present_in_path", "never_called",
                    "not_wired_in", "not_invoked", "cannot_be_found", "not_used"):
        assert normalise_status(negated) == "absent", negated

    for affirmed in ("code_exists_elsewhere", "capability_present", "wired_in",
                     "invoked_from_abandon", "already_implemented"):
        assert normalise_status(affirmed) == "exists", affirmed

    # Negation with nothing to negate is still not a verdict.
    assert normalise_status("no idea") is None
