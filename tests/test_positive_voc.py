"""Positive-signal analysis (2026-09-04): the mirror of the existing
negative-only funnel/VoC pipeline — phase1.strongest_stage() and the
positive-review classification path (semantic_voc.classify_reviews(polarity=
"positive") + phase3_voc.run_positive_voc), which together ground
growth_ideas in what's already working, not just what's broken."""
from app.agents.analyst import phase1
from app.agents.analyst.phase3_voc import classify_review, run_positive_voc
from app.agents.analyst.semantic_voc import classify_reviews

POSITIVE_THEMES = [
    {"name": "fast_delivery", "routing_stage": "delivery", "keywords": ["cepat", "kilat"]},
    {"name": "easy_checkout", "routing_stage": "pharmacy_checkout", "keywords": ["mudah", "praktis"]},
]


def test_strongest_stage_picks_the_best_converting_transition():
    table = [
        {"stage": "created", "count": 1000, "conversion_from_previous": None},
        {"stage": "confirmed", "count": 950, "conversion_from_previous": 0.95},
        {"stage": "delivered", "count": 200, "conversion_from_previous": 0.2105},
    ]
    best = phase1.strongest_stage(table)
    assert best["from_stage"] == "created"
    assert best["to_stage"] == "confirmed"
    assert best["conversion_rate"] == 0.95


def test_strongest_stage_is_none_for_a_single_stage_table():
    assert phase1.strongest_stage([{"stage": "created", "count": 100, "conversion_from_previous": None}]) is None


def _positive_llm(theme="fast_delivery"):
    def llm(ctx):
        assert ctx["reviews_batch"]["polarity"] == "positive"
        return {"classifications": [
            {"review_id": r["review_id"], "theme": theme, "stage": "delivery",
             "severity": "high", "matched_phrase": "cepat", "english_gloss": "fast delivery"}
            for r in ctx["reviews_batch"]["reviews"]]}
    return llm


def test_classify_reviews_positive_polarity_only_sends_high_scoring_reviews():
    reviews = [
        {"review_id": "0", "text": "cepat sekali", "score": 5},
        {"review_id": "1", "text": "biasa saja", "score": 3},
        {"review_id": "2", "text": "buruk sekali", "score": 1},
    ]
    seen = []

    def counting(ctx):
        seen.extend(r["review_id"] for r in ctx["reviews_batch"]["reviews"])
        return _positive_llm()(ctx)

    themes, meta = classify_reviews(counting, reviews, POSITIVE_THEMES, classify_review, polarity="positive")

    assert seen == ["0"]  # only the score>=4 review was sent
    assert themes[0] == "fast_delivery"
    assert themes[1] == "unmapped"
    assert themes[2] == "unmapped"
    assert meta["polarity"] == "positive"


def test_classify_reviews_negative_polarity_is_unchanged_by_default():
    reviews = [{"review_id": "0", "text": "buruk", "score": 1}]

    def llm(ctx):
        assert ctx["reviews_batch"]["polarity"] == "negative"
        return {"classifications": [{"review_id": "0", "theme": "price", "stage": "pharmacy_checkout",
                                     "severity": "high", "matched_phrase": "x", "english_gloss": "y"}]}

    themes, meta = classify_reviews(llm, reviews, POSITIVE_THEMES, classify_review)
    assert meta["polarity"] == "negative"


def test_run_positive_voc_buckets_by_theme_and_never_escalates():
    reviews = [{"text": "cepat", "score": 5, "at": "2026-08-10"} for _ in range(3)] + \
              [{"text": "mudah dipakai", "score": 4, "at": "2026-08-11"}] + \
              [{"text": "lumayan", "score": 3, "at": "2026-08-11"}]  # below POSITIVE_MIN_SCORE, excluded

    signals = run_positive_voc(reviews, POSITIVE_THEMES)

    by_theme = {s["theme"]: s["count"] for s in signals}
    assert by_theme.get("fast_delivery") == 3
    assert by_theme.get("easy_checkout") == 1
    assert "unmapped" not in by_theme  # never a first-class signal, unlike run_voc's themes
    assert sum(by_theme.values()) == 4  # the score=3 review never counted


def test_run_positive_voc_prefers_supplied_classifications_over_lexicon():
    reviews = [{"text": "no keyword here at all", "score": 5, "at": "2026-08-10"}]
    signals = run_positive_voc(reviews, POSITIVE_THEMES, themes_per_review=["fast_delivery"])
    assert signals == [{"theme": "fast_delivery", "count": 1,
                        "sample_quotes": ["[5★ 2026-08-10] no keyword here at all"]}]
