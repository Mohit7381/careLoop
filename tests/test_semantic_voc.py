"""Semantic review classification, and the window it runs over."""
import json
from pathlib import Path

import yaml

from app.agents.analyst.phase3_voc import classify_review, filter_by_days
from app.agents.analyst.semantic_voc import BATCH_SIZE, classify_reviews

ROOT = Path(__file__).parent.parent
CFG = yaml.safe_load((ROOT / "config/journeys/pd_checkout.yaml").read_text())
THEMES = CFG["voc"]["themes"]
REVIEWS = json.loads((ROOT / "fixtures/pd_checkout/reviews_scrubbed.json").read_text())


def _llm(theme="payment/refund"):
    def llm(ctx):
        return {"classifications": [
            {"review_id": r["review_id"], "theme": theme, "stage": "payments",
             "severity": "high", "matched_phrase": "uang belum kembali",
             "english_gloss": "money has not come back"}
            for r in ctx["reviews_batch"]["reviews"]]}
    return llm


def test_indonesian_morphology_defeats_substring_matching():
    """A real review from the corpus that the lexicon cannot reach.

    "lama pengiriman nya" is "its delivery is slow" — plainly delivery/order.
    The lexicon looks for `kirim`, but the noun form is peng-irim-an, so the
    substring is not there. 9 of the 92 negative reviews in the fixture are
    unmapped for reasons like this, and every one of them is a complaint the
    escalation counts never see.
    """
    review = [{"text": "lama pengiriman nya", "score": 1}]
    assert classify_review(review[0]["text"], THEMES) == "unmapped"

    themes, meta = classify_reviews(_llm("delivery/order"), review, THEMES, classify_review)
    assert themes == ["delivery/order"]
    assert meta["classifier"] == "semantic"


def test_the_lexicon_leaves_real_complaints_uncounted():
    """Quantifies the gap this replaces, against the frozen corpus."""
    negatives = [r for r in REVIEWS if int(r.get("score", 5)) <= 2]
    unmapped = [r for r in negatives if classify_review(r["text"], THEMES) == "unmapped"]
    assert len(unmapped) >= 5, "fixture changed — re-check the premise for semantic VoC"
    assert any("pengiriman" in r["text"] for r in unmapped)


def test_an_indonesian_call_is_auditable_in_english():
    """matched_phrase + english_gloss are what the keyword list could never give
    us: a reviewer who does not read Indonesian can still check the call."""
    _, meta = classify_reviews(_llm(), REVIEWS[:3], THEMES, classify_review)
    assert meta["matched_phrases"] and meta["glosses"]


def test_a_failed_batch_degrades_to_the_lexicon_not_to_silence():
    """An empty bucket reads as "no complaints", which is a claim. Falling back
    to keywords is worse analysis; falling back to nothing is a false one."""
    def boom(ctx):
        raise RuntimeError("sphere unavailable")
    themes, meta = classify_reviews(boom, REVIEWS[:5], THEMES, classify_review)
    assert len(themes) == 5
    assert all(t for t in themes)
    assert meta["classifier"] == "lexical"


def test_an_invented_theme_is_rejected():
    """The taxonomy is closed — the model cannot add to it."""
    rogue = lambda ctx: {"classifications": [
        {"review_id": r["review_id"], "theme": "vibes", "stage": None, "severity": "low",
         "matched_phrase": "x", "english_gloss": "y"}
        for r in ctx["reviews_batch"]["reviews"]]}
    themes, _ = classify_reviews(rogue, REVIEWS[:2], THEMES, classify_review)
    assert "vibes" not in themes


def test_batching_covers_every_review_exactly_once():
    seen = []

    def counting(ctx):
        seen.extend(r["review_id"] for r in ctx["reviews_batch"]["reviews"])
        return _llm()(ctx)

    themes, meta = classify_reviews(counting, REVIEWS, THEMES, classify_review)
    assert len(themes) == len(REVIEWS)
    assert sorted(map(int, seen)) == list(range(len(REVIEWS)))
    assert meta["batches"] == -(-len(REVIEWS) // BATCH_SIZE)


# --- the review window ---

def test_the_window_is_anchored_to_the_corpus_not_to_today():
    """The fixture is a frozen capture. Anchoring to now() would quietly return
    nothing once it ages past the window."""
    kept, meta = filter_by_days(REVIEWS, 7)
    assert 0 < len(kept) < len(REVIEWS)
    assert meta["review_window_to"] == max(str(r["at"])[:10] for r in REVIEWS)
    assert meta["reviews_available"] == len(REVIEWS)


def test_no_window_keeps_everything():
    kept, meta = filter_by_days(REVIEWS, None)
    assert len(kept) == len(REVIEWS) and meta == {}


def test_a_wider_window_never_returns_less():
    assert len(filter_by_days(REVIEWS, 30)[0]) >= len(filter_by_days(REVIEWS, 7)[0])
