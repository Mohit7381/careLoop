"""
Prompt-scoped analysis (decision #13, contracts.py) — resolves free text
like "analyze cart abandonment dropoff" into the structured `dimensions`
list POST /runs already accepts, so a caller doesn't need to already know
the journey's routing-category names.

Deliberately rule-based rather than another LLM call: the categories are a
small, fixed, known set (the journey's own `routing:` keys in
config/journeys/{journey}.yaml), and a wrong guess here silently narrows
what a run even looks at. Same "insufficient data is a valid, honest
output" discipline as prd_editor.py's chat-edit fallback — no confident
match means saying so and listing the real categories, never guessing.
"""
from app.journeys import load_journey

# English synonyms per routing category. The categories themselves come
# from the journey config (stable, per-journey), but nobody types
# "pharmacy_checkout" verbatim — this is the vocabulary a person actually
# uses to talk about them.
_SYNONYMS: dict[str, list[str]] = {
    "pharmacy_checkout": [
        "checkout", "cart abandon", "cart abandonment", "abandoned cart",
        "pharmacy checkout", "prescription checkout", "cart",
    ],
    "payments": ["payment", "refund", "billing", "transaction", "pay"],
    "delivery": ["delivery", "shipping", "courier", "logistics", "shipment"],
    "stock": ["stock", "inventory", "out of stock", "unavailable", "availability"],
    "re_engagement": ["re-engagement", "reengagement", "winback", "win-back", "retention"],
    "consultation": ["consultation", "consult", "doctor", "prescription", "telemedicine", "rx"],
}


def resolve_dimensions(journey: str, message: str) -> tuple[list[str], str]:
    """Returns (dimensions, reply). dimensions is [] when nothing matched —
    an honest empty result, never a guess at "the whole journey" instead."""
    cfg = load_journey(journey)
    routing_keys = list(cfg["routing"].keys())
    text = (message or "").lower()

    matched = [
        key for key in routing_keys
        if key.replace("_", " ") in text or any(term in text for term in _SYNONYMS.get(key, []))
    ]

    if not matched:
        options = ", ".join(routing_keys)
        return [], (
            f"I couldn't match that to a routing category for '{journey}'. "
            f"Try naming one directly, or a close synonym. Valid categories: {options}."
        )

    return matched, f"Scoped to: {', '.join(matched)}."
