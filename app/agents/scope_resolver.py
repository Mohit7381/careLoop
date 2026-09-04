"""Turn a user's sentence into constraints the pipeline can obey.

    "why are users dropping off after adding items to cart"
        -> from_stage=created, to_stage=confirmed,
           matched_on=["pharmacy.click.add_to_cart_button"]

This is deliberately deterministic. `phase1.largest_drop` picks the target gap
by arithmetic, and that is the reason the headline number cannot be argued into
existence — so a prompt is resolved into constraints and shown back for
confirmation, never handed to the Analyst as prose to interpret.

Resolution is transparent for the same reason: `matched_on` says which piece of
journey vocabulary each decision came from, and `unresolved` names anything the
user asked for that we could not honour, so a misreading is visible before it
costs a run rather than after.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.schemas.contracts import RunScope

_MIN_TOKEN = 4
_STOP = {
    # "transactions" is the generic object of a growth question, not a reference
    # to the backend.transaction_* events — it must not anchor a stage.
    "transaction", "transactions",
    "want", "data", "analysis", "why", "the", "for", "are", "users", "user",
    "dropping", "drop", "dropped", "after", "before", "from", "into", "with",
    "show", "give", "run", "please", "them", "this", "that", "what", "where",
    "happening", "going", "look", "into", "much", "many", "just", "only",
    "last", "past", "days", "day", "week", "weeks", "review", "reviews",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z_]{%d,}" % _MIN_TOKEN, (text or "").lower())
            if w not in _STOP}


def _label_tokens(label: str) -> set[str]:
    """Journey vocabulary is dotted and underscored — split on both."""
    return {w for w in re.split(r"[._\s-]+", label.lower()) if len(w) >= _MIN_TOKEN}


def _shares_stem(a: str, b: str) -> bool:
    """Same prefix rule journey_events_for uses.

    Exact token equality cannot match "payments" against the event token
    "payment", which is how a perfectly ordinary request — "why are users
    dropping off during the payments" — resolved to nothing at all. A shared
    4-character prefix handles plurals and simple inflection without pulling in
    a stemmer, and is short enough that "page" and "paginate" stay distinct.
    """
    return a[:_MIN_TOKEN] == b[:_MIN_TOKEN]


def _overlaps(label_tokens: set[str], words: set[str]) -> bool:
    return any(_shares_stem(lt, w) for lt in label_tokens for w in words)


_GROWTH_WORDS = {
    "increase", "increasing", "grow", "growing", "growth", "boost", "boosting", "expand", "expanding",
    "more", "improve", "improving", "lift", "raise", "acquire", "acquisition", "upsell", "revenue",
    "tambah", "meningkatkan", "naikkan", "pertumbuhan",          # id: add / increase / raise / growth
}
_GROWTH_OBJECTS = {"transaction", "transactions", "orders", "bookings", "consultations", "consults", "sales",
                   "conversion", "conversions", "volume", "revenue", "users", "customers", "adoption", "retention"}


def resolve_intent(prompt: str) -> tuple[str, list[str]]:
    """"how can I increase transactions on consultations" is a growth question,
    not a drop-off diagnosis. Deterministic, like everything else here: a growth
    verb next to a growth object. Returns (intent, matched words). The intent
    changes what the Analyst is asked to prioritise (which cuts, which growth
    ideas), never which numbers it is shown."""
    words = set(re.findall(r"[a-z]+", (prompt or "").lower()))
    verbs = sorted(words & _GROWTH_WORDS)
    objects = sorted(words & _GROWTH_OBJECTS)
    if verbs and objects:
        return "growth", verbs + objects
    return "diagnosis", []


def _review_days(prompt: str) -> Optional[int]:
    """"past 10-15 days" -> 15. A range resolves to its upper bound: the user is
    describing roughly how far back to look, and fetching the wider window and
    reporting the real span is honest, where fetching the narrower one silently
    answers a different question."""
    m = re.search(r"(?:last|past|previous)\s+(\d+)\s*(?:-|–|to)\s*(\d+)\s*day", prompt, re.I)
    if m:
        return max(int(m.group(1)), int(m.group(2)))
    m = re.search(r"(?:last|past|previous)\s+(\d+)\s*day", prompt, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:last|past|previous)\s+(\d+)\s*week", prompt, re.I)
    if m:
        return int(m.group(1)) * 7
    return None


def pick_journey(prompt: str, journeys: dict[str, dict], default: str = "pd_checkout") -> tuple[str, list[str]]:
    """Choose the journey a prompt is about, from each journey's own
    `journey_keywords`. Returns (journey, matched_keywords).

    Deterministic and explained, like the rest of scope resolution: the winner
    is the journey with the most keyword hits; a tie or no hits falls back to
    `default`. "payment" is in neither list on purpose — both journeys have a
    payment step, so it must not decide between them.
    """
    words = _tokens(prompt) | set(re.findall(r"[a-z]{2,3}\b", (prompt or "").lower()))
    best, best_hits = default, []
    for name, cfg in journeys.items():
        kws = [k.lower() for k in (cfg.get("journey_keywords") or [])]
        hits = sorted({k for k in kws if any(_shares_stem(k, w) if len(k) >= _MIN_TOKEN else k == w for w in words)})
        if len(hits) > len(best_hits):
            best, best_hits = name, hits
    return best, best_hits


def resolve_scope(prompt: str, journey_cfg: dict, ct_event_names: list[str],
                  available_dimensions: list[str]) -> RunScope:
    """Resolve `prompt` against this journey's own vocabulary.

    Nothing is invented: a stage has to be named in journey_cfg, a dimension has
    to be one the AggregateTool can actually answer, and an event has to be one
    the snapshot really carries.
    """
    scope = RunScope(prompt=prompt)
    if not (prompt or "").strip():
        return scope

    words = _tokens(prompt)

    # --- reviews: how far back ---
    scope.review_days = _review_days(prompt)

    # --- intent: diagnosis (default) or growth ---
    intent, hits = resolve_intent(prompt)
    scope.intent = intent
    if intent == "growth":
        scope.matched_on.append(f"intent:growth (via {', '.join(hits)})")

    # --- dimensions the user named, by name or by how people actually say it ---
    aliases: dict[str, list[str]] = journey_cfg.get("dimension_aliases") or {}
    lowered = (prompt or "").lower()
    # A dimension is not "named" by a word that merely names the journey.
    # "why do consultations get abandoned" matched consultation_trigger on the
    # token "consultation" and pinned the whole drill-down to the weakest cut.
    journey_words = {k.lower() for k in (journey_cfg.get("journey_keywords") or [])}
    for dim in available_dimensions:
        hit = None
        dim_tokens = {t for t in _label_tokens(dim)
                      if not any(_shares_stem(t, jw) for jw in journey_words if len(jw) >= _MIN_TOKEN)}
        if _overlaps(dim_tokens, words):
            hit = dim
        else:
            for alias in aliases.get(dim, []):
                # multi-word aliases ("out of stock") need a substring test
                if (" " in alias and alias in lowered) or \
                   (" " not in alias and any(_shares_stem(alias, w) for w in words)):
                    hit = alias
                    break
        if hit:
            scope.dimensions.append(dim)
            scope.matched_on.append(f"dimension:{dim}" + ("" if hit == dim else f" (via '{hit}')"))

    # --- which funnel transition ---
    stages: list[str] = list(journey_cfg.get("stages") or [])
    hit_stages = [st for st in stages if _overlaps(_label_tokens(st), words)]

    # Events are the richer vocabulary: "adding items to cart" matches
    # pharmacy.click.add_to_cart_button long before it matches any stage name.
    event_stage = journey_cfg.get("event_stage") or {}
    # An event is not "named" by the namespace every event of this journey
    # carries ("consultation" in consultation.view.payment_page): "how can I
    # increase transactions on consultations" matched all 19 consultation.*
    # events on that token and the confirm box showed twenty chips that said
    # nothing. Only tokens shared by (nearly) every event are stripped, so
    # "cart" in pharmacy.click.add_to_cart_button still anchors a stage.
    token_sets = [_label_tokens(e) for e in ct_event_names]
    namespace = {t for t in set().union(*token_sets)
                 if sum(t in ts for ts in token_sets) >= 0.8 * len(token_sets)} if token_sets else set()
    hit_events = [e for e, ts in zip(ct_event_names, token_sets) if _overlaps(ts - namespace, words)]
    for ev in hit_events:
        scope.matched_on.append(f"event:{ev}")

    anchor: Optional[str] = None
    if hit_events:
        mapped = [event_stage.get(e) for e in hit_events if event_stage.get(e) in stages]
        anchor = mapped[0] if mapped else None
    if anchor is None and hit_stages:
        anchor = hit_stages[0]

    if anchor is not None:
        i = stages.index(anchor)
        # "after X" means the transition leaving X; if X is terminal, the one into it.
        if i < len(stages) - 1:
            scope.from_stage, scope.to_stage = stages[i], stages[i + 1]
        elif i > 0:
            scope.from_stage, scope.to_stage = stages[i - 1], stages[i]
        scope.matched_on.append(f"stage:{anchor}")

    # --- say what we could not honour ---
    if not scope.is_scoped() and not hit_events:
        scope.unresolved.append(
            "nothing in the request matched this journey's stages, events or dimensions")
    if hit_events and anchor is None:
        scope.unresolved.append(
            f"matched events {hit_events} but none maps to a funnel stage — "
            f"add them to journey_events/event_stage in the journey config")
    return scope


def describe(scope: RunScope, journey: Optional[str] = None) -> str:
    """One line a human can confirm or reject before the run starts."""
    where = f" ({journey.replace('_', ' ')} journey)" if journey else ""
    growth = " Read as a growth question: the Analyst will prioritise growth ideas alongside the drop-off findings." \
        if getattr(scope, "intent", "diagnosis") == "growth" else ""
    if not scope.is_scoped():
        return f"Could not scope this request — the full funnel will be analysed{where}.{growth}"
    bits = []
    if scope.from_stage:
        bits.append(f"the {scope.from_stage} to {scope.to_stage} drop")
    if scope.dimensions:
        bits.append("cut by " + ", ".join(scope.dimensions))
    if scope.review_days:
        bits.append(f"reviews from the last {scope.review_days} days")
    return "Analysing " + "; ".join(bits) + f"{where}.{growth}"
