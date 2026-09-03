"""Derives Finding.journey_events (contracts v3 decision #11) from the
Fetcher's own ct_events - the real analytics event names bounding a
drop-off, straight from the analytics pipeline, rather than parsed out of
free-text hypothesis prose.

PR #3 review D1.2: Code Scout's search-term proposal falls back to
splitting the hypothesis on whitespace when journey_events is empty - on
real findings this handed GitLab prose words ("sizable", "portion",
"captured") that hit doc files before any real source. The two ct_events
that DID return real hits in that live run, order_abandoned and
order_placed, are exactly the ones whose event name shares a real word
with the finding's own hypothesis text - "abandon"/"abandoned",
"order"/"orders".

This is a deterministic heuristic, not an LLM call - safer to ship now than
inventing a new LLM output field on a prompt template nobody's confirmed
supports it. An event is relevant to a finding if a keyword from its
event_name (split on "_", 4+ chars) shares a >=4-char prefix with a word in
the finding's hypothesis - handles exact matches (cart/cart) and simple
inflections (abandon/abandoned) without a stemming library. Conservative by
design: a finding with no textual overlap gets no journey_events and falls
back to whatever the assessor already does for that case (theme_search_terms
for VoC, hypothesis-splitting otherwise) - never forces a guess.
"""
from __future__ import annotations

import re

from app.schemas.contracts import CtEventRow, Finding

_MIN_STEM_LEN = 4


def _shares_stem(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return len(a) >= _MIN_STEM_LEN and len(b) >= _MIN_STEM_LEN and a[:_MIN_STEM_LEN] == b[:_MIN_STEM_LEN]


def journey_events_for(finding: Finding, ct_events: list[CtEventRow]) -> list[str]:
    """Best-effort, deterministic derivation - warehouse-origin findings
    only; VoC findings already have their own theme_search_terms (journey
    config's voc.themes[].search_terms) as real search seed material."""
    if finding.origin != "warehouse" or not ct_events:
        return []
    hypothesis_words = re.findall(r"[a-zA-Z]{4,}", finding.hypothesis)
    matches: list[str] = []
    for event in ct_events:
        # Split on BOTH separators. Real CT names are dotted-and-underscored
        # ("pharmacy.click.add_to_cart_button"); splitting on "_" alone leaves
        # "pharmacy.click.add" as one token, so "cart" never surfaces and the
        # cart events stop matching a cart hypothesis entirely.
        event_keywords = [w for w in re.split(r"[._]", event.event_name)
                          if len(w) >= _MIN_STEM_LEN]
        if any(_shares_stem(kw, hw) for kw in event_keywords for hw in hypothesis_words):
            matches.append(event.event_name)
    return matches
