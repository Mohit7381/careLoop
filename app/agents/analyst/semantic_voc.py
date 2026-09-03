"""Semantic review classification, replacing keyword matching.

The lexical classifier in phase3_voc matches substrings from a hand-written
Bahasa Indonesia keyword list. It cannot see meaning: a review saying "uang
saya belum kembali sampai sekarang" (my money still has not come back) carries
no word from the payment/refund list, and a review mentioning "dokter" in
passing is counted as a consultation complaint.

This uses the `voc-theme-classification` sphere use case (template 21688),
which was provisioned for exactly this and had never been called. The model
reads the review, assigns one theme from the journey's own taxonomy, and — the
part the lexicon could never give us — returns the phrase it matched on and an
English gloss, so an Indonesian classification is auditable by a reviewer who
does not read Indonesian.

Why this and not a vector index: sphere exposes no embeddings endpoint, and the
corpus is Indonesian, where a naive multilingual embedding would be the weakest
link. The LLM is doing the semantic work either way; this skips the index.

Falls back to the lexical classifier per batch. A theme count is evidence that
gets escalated to Code Scout, so a failed batch must degrade to the old
behaviour, never to an empty bucket that reads as "no complaints".
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("careloop.semantic_voc")

BATCH_SIZE = 40          # keeps each call well inside the context and the output schema small
MAX_TEXT_CHARS = 400     # reviews are short; this only guards a pathological one

LLMCall = Callable[[dict[str, Any]], dict[str, Any]]


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield i, items[i:i + size]


def classify_reviews(llm: Optional[LLMCall], reviews: list[dict], themes_cfg: list[dict],
                     lexical_fallback: Callable[[str, list[dict]], str],
                     scope_hint: Optional[str] = None) -> tuple[list[str], dict]:
    """Returns (theme per review, meta). Order matches `reviews`.

    `scope_hint` is the user's own words when the run is scoped. It biases which
    theme a genuinely ambiguous review lands in; it cannot invent a theme,
    because the taxonomy is closed and anything outside it is 'unmapped'.
    """
    taxonomy = [{"name": t["name"], "routing_stage": t["routing_stage"],
                 "examples": t.get("keywords", [])[:6]} for t in themes_cfg]
    out: list[str] = [""] * len(reviews)
    meta = {"classifier": "semantic", "batches": 0, "fallback_batches": 0,
            "glosses": {}, "matched_phrases": {}}

    if llm is None:
        return [lexical_fallback(r.get("text", ""), themes_cfg) for r in reviews], \
               {**meta, "classifier": "lexical", "reason": "no llm configured"}

    valid = {t["name"] for t in themes_cfg} | {"unmapped"}

    for offset, batch in _batches(reviews, BATCH_SIZE):
        meta["batches"] += 1
        payload = {
            "taxonomy": taxonomy,
            "scope_hint": scope_hint or "",
            "reviews": [{"review_id": str(offset + i),
                         "text": (r.get("text") or "")[:MAX_TEXT_CHARS],
                         "rating": r.get("score")}
                        for i, r in enumerate(batch)],
        }
        try:
            res = llm({"reviews_batch": payload})
            rows = {str(c["review_id"]): c for c in (res.get("classifications") or [])}
        except Exception as exc:
            logger.warning("semantic VoC batch at %d failed (%s) — lexical for this batch",
                           offset, exc)
            rows = {}

        missing = 0
        for i, r in enumerate(batch):
            row = rows.get(str(offset + i))
            theme = (row or {}).get("theme")
            if theme not in valid:
                missing += 1
                out[offset + i] = lexical_fallback(r.get("text", ""), themes_cfg)
                continue
            out[offset + i] = theme
            if row.get("english_gloss"):
                meta["glosses"][str(offset + i)] = row["english_gloss"]
            if row.get("matched_phrase"):
                meta["matched_phrases"][str(offset + i)] = row["matched_phrase"]
        if missing == len(batch):
            meta["fallback_batches"] += 1

    if meta["fallback_batches"] == meta["batches"]:
        meta["classifier"] = "lexical"
        meta["reason"] = "every batch fell back"
    elif meta["fallback_batches"]:
        meta["classifier"] = "semantic_partial"
    return out, meta
