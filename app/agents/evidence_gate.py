"""Evidence gate for generated prose.

The Analyst has been under this rule since day one: a finding may only cite
numbers the model was actually shown. The Reporter's narrative and the PRD are
the two places where a model writes free text that a human then reads, approves
and forwards — so the same rule applies, checked the same way.

Structural numbers are exempt (section numbers, FR-01, "at most 2 quotes"), as
are dates, which are formatting rather than claims. Everything above
STRUCTURAL_MAX has to be traceable to an input.

Percentages are matched in both directions: a model shown a rate of 0.3654 may
legitimately write "36.5%", and one shown 36.5 may write "0.365".
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.analyst.validator import collect_numbers

# Below this, a bare integer is assumed to be structure ("Section 3", "FR-07",
# "up to 2 quotes", "a 5% uplift") rather than a claim about the data. Every
# real magnitude in this pipeline — review counts, order counts, rates as
# percentages — lands above it.
STRUCTURAL_MAX = 20.0

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_LABELLED = re.compile(r"\b(?:FR|NFR|OQ|G)-?\d+\b", re.I)
# Not preceded by a word character: "p95", "v2" and "utf8" are identifiers, not
# magnitudes — the same glued-digits rule the Analyst's evidence extractor uses.
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*")

# Numbers that are not claims about the data, however large: HTTP status codes
# ("result: 200/400", "HTTP 200 OK", "returns 404"), and any value carrying a
# unit of time, size, rate or percent ("p95 under 200 ms", "50 KB", "95%").
# A live PRD draft was refused in its entirety for "result: 200/400" in its
# API-contract section. A bare count ("200 orders") is still a claim.
_STATUS_CODES = re.compile(
    r"(?:\b(?:HTTP|status(?:\s+code)?|result|returns?|responds?\s+with)\s*:?\s*)?"
    r"\b[1-5]\d{2}(?:\s*/\s*[1-5]\d{2})+\b"                 # 200/400, 200/404/500
    r"|\b(?:HTTP|status(?:\s+code)?|result|returns?|responds?\s+with)\s*:?\s*[1-5]\d{2}\b"
    r"|\b[1-5]\d{2}\s+(?:OK|Created|Accepted|No Content|Bad Request|Unauthorized|Forbidden|"
    r"Not Found|Conflict|Unprocessable|Too Many Requests|Internal Server Error)\b",
    re.I,
)
_WITH_UNIT = re.compile(
    r"-?\d[\d,]*\.?\d*\s*(?:ms|msec|milliseconds?|s|sec|seconds?|min|minutes?|h|hrs?|hours?|"
    r"d|days?|wks?|weeks?|px|kb|mb|gb|tb|rps|qps|tps|req/s|%|pp|x)(?=$|[^\w])",
    re.I,
)


def _strip_non_claims(text: str) -> str:
    text = _DATE.sub(" ", text or "")
    text = _LABELLED.sub(" ", text)
    text = _STATUS_CODES.sub(" ", text)
    text = _WITH_UNIT.sub(" ", text)
    return text


def numbers_in_text(text: str) -> set[float]:
    """Every number a reader would see as a claim about the data."""
    stripped = _strip_non_claims(text)
    out: set[float] = set()
    for raw in _NUMBER.findall(stripped):
        try:
            out.add(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _supported(value: float, allowed: set[float]) -> bool:
    for a in allowed:
        # exact, or the same quantity expressed as a percentage either way
        for candidate in (a, a * 100.0, a / 100.0):
            if abs(value - candidate) <= max(0.05, abs(candidate) * 0.001):
                return True
    return False


def _string_leaves(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [t for v in obj.values() for t in _string_leaves(v)]
    if isinstance(obj, (list, tuple)):
        return [t for v in obj for t in _string_leaves(v)]
    return []


def shown_numbers(inputs: Any) -> set[float]:
    """Every number the model could legitimately repeat: numeric leaves AND
    numbers embedded in the strings it was given.

    The first live PRD run was rejected for citing 647,191 / 229,622 / 315,934
    — the funnel counts — because they live inside evidence `metric` strings
    ("1_item entered 315,934 converted 139,707 rate 0.4422") and only the
    `value` float was whitelisted. The model quoted what it was shown, and the
    gate threw the draft away. A reviewer's quote saying "61rb" is shown text
    too; repeating it is not inventing a number.
    """
    allowed = set(collect_numbers(inputs))
    for text in _string_leaves(inputs):
        allowed |= numbers_in_text(text)
    return allowed


def unsupported_numbers(text: str, inputs: Any) -> list[float]:
    """Numbers in `text` that do not trace back to anything in `inputs`.

    Empty list means the prose is fully grounded. Callers treat a non-empty
    result as "do not ship this text", not as "correct it" — silently editing a
    model's numbers would hide the fact that it invented one.
    """
    allowed = shown_numbers(inputs)
    return sorted(v for v in numbers_in_text(text)
                  if abs(v) > STRUCTURAL_MAX and not _supported(v, allowed))
