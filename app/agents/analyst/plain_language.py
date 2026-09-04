"""Plain words for the numbers the Analyst cites.

The model is told to WRITE for a product or ops reader (template 21687 v13),
but its evidence list is still the raw rows it was shown — JSON like
{"segment": "cash", "entered": 154950, "converted": 72093, "rate": 0.4653} —
because that is how the evidence gate traces a number back to shown data.
This turns each cited row into one readable sentence for the UI and the
report, keeping the raw string alongside as the audit trail.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

_NUM_PAIR = re.compile(r'([a-z_]+)"?\s*:\s*(-?\d[\d,]*\.?\d*)(?![\w.])')
_STR_PAIR = re.compile(r'([a-z_]+)"?\s*:\s*"?([A-Za-z][^,{}":]*)')


def _fields(raw: str) -> dict[str, Any]:
    """Tolerant: real JSON first; otherwise every `key: number` and `key: word`
    pair in the text — the model often echoes a row as prose and appends a
    stray ': 0.4', e.g. 'top_gap: lost: 87511, share_of_prev: 0.3862: 0.4'."""
    s = raw.strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    out: dict[str, Any] = {}
    for k, v in _NUM_PAIR.findall(s):
        try:
            out[k] = float(v.replace(",", ""))
        except ValueError:
            pass
    for k, v in _STR_PAIR.findall(s):
        if k not in out and v.strip() and not re.fullmatch(r"[a-z_]+", v.strip()) or (k not in out and k in ("segment", "stage", "reason", "theme")):
            out[k] = v.strip()
    return out


def _n(v: Any) -> str:
    try:
        f = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return str(v)
    return f"{int(round(f)):,}" if f == int(f) or f >= 100 else f"{f:g}"


def _pct(v: Any) -> Optional[str]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f"{f * 100:.1f}%" if 0 <= f <= 1 else None


_OBJ = re.compile(r"\{[^{}]*\}")


def humanise_evidence(raw: str, stage_labels: Optional[dict] = None,
                      dimension_labels: Optional[dict] = None, dimension: Optional[str] = None) -> str:
    """One readable sentence per cited row; falls back to the raw text.

    The model sometimes cites several rows in one string
    ('phase1 funnel: {...}, {...}: 0.6'); each object is translated and they
    are joined with '; ' so a stage count is never attributed to the wrong stage."""
    # a reason cluster cited as '"abandoned by system": 54015' — the key IS the reason
    m = re.fullmatch(r'\s*"([^"]+)"\s*:\s*(-?\d[\d,]*\.?\d*)\s*', raw)
    if m and not m.group(1).replace("_", "").isalnum():
        return f"{_n(m.group(2))} left with the reason '{m.group(1)}'"
    objs = _OBJ.findall(raw)
    if len(objs) > 1:
        parts = [humanise_evidence(o, stage_labels, dimension_labels, dimension) for o in objs]
        return "; ".join(parts)
    stage_labels = stage_labels or {}
    dimension_labels = dimension_labels or {}
    f = _fields(objs[0] if objs else raw)
    if not f:
        return raw

    def stage(name: Any) -> str:
        return stage_labels.get(str(name), str(name).replace("_", " "))

    # a cohort row: segment / entered / converted / rate
    if "segment" in f and "entered" in f:
        seg = str(f["segment"]).replace("_", " ")
        dim = f" ({dimension_labels.get(dimension, dimension)})" if dimension else ""
        part = f"{seg}{dim}: {_n(f['entered'])} people"
        if "converted" in f:
            part += f", {_n(f['converted'])} went on to the next step"
            if _pct(f.get("rate")):
                part += f" ({_pct(f['rate'])})"
        return part
    # the top gap: from/to stage with entered/converted/lost
    if "lost" in f and ("from_stage" in f or "share_of_prev" in f or "entered" in f):
        frm, to = f.get("from_stage"), f.get("to_stage")
        head = f"between '{stage(frm)}' and '{stage(to)}'" if frm and to else "at the biggest drop"
        s = f"{_n(f['lost'])} people were lost {head}"
        if "entered" in f:
            s += f" out of {_n(f['entered'])}"
        rate = _pct(f.get("conversion_from_previous"))
        if rate:
            s += f" ({rate} continued)"
        return s
    # a funnel stage row: stage / count / conversion_from_previous
    if "stage" in f and "count" in f:
        s = f"{_n(f['count'])} people {stage(f['stage'])}"
        rate = _pct(f.get("conversion_from_previous"))
        if rate:
            s += f" ({rate} of the previous step)"
        return s
    # a recorded reason
    for key in ("reason", "cancellation_reason", "abandonment_reason", "abandon_reason"):
        if key in f and "count" in f:
            return f"{_n(f['count'])} left with the reason '{f[key]}'"
    if "theme" in f and "count" in f:
        return f"{_n(f['count'])} reviews on the theme '{f['theme']}'"
    return raw
