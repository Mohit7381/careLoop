"""
Chat-style PRD editing. OWNER: Mohit.

A human reviewing a DRAFT PRD can ask for a change in plain language
instead of hand-editing markdown. Two tiers:

  fast paths (no network, always available)
    - "title: <new title>" / "rename title to <new title>" -> renames the H1
    - "remove FR-<n>" / "delete FR-<n>" -> drops that functional requirement row

  everything else -> a real rewrite through the dedicated `prd-chat-edit`
    sphere use case (project 7121, use case 12870, template 21791: it receives
    original_markdown + instruction and returns prd_markdown + a one-line
    reply for the chat). The rewrite is accepted only if it is a complete
    document and every number it cites was already in the document or the
    instruction — the same evidence gate the generator uses — and the DRAFT
    banner is ours, re-inserted if the model dropped it. When no model is
    available (demo mode without LIVE_LLM) or the draft is rejected, the
    request is appended to Open Questions as a flagged item and the reply
    says exactly why, rather than pretending an edit was made.
"""
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.agents.evidence_gate import unsupported_numbers

logger = logging.getLogger("careloop.prd_editor")
LLMCall = Callable[[dict[str, Any]], dict[str, Any]]

MIN_REVISION_CHARS = 200          # anything shorter is a truncated or empty draft


@dataclass
class EditResult:
    markdown: str
    reply: str
    applied: bool


_TITLE_RE = re.compile(r"^(?:title:\s*|rename title to\s+)(.+)$", re.IGNORECASE)
_REMOVE_FR_RE = re.compile(r"\b(?:remove|delete)\s+fr[-\s]?(\d+)\b", re.IGNORECASE)
_BANNER_RE = re.compile(r"^>\s*\*\*DRAFT", re.MULTILINE)


def apply_edit_instruction(markdown: str, message: str, llm: Optional[LLMCall] = None) -> EditResult:
    message = message.strip()

    title_match = _TITLE_RE.match(message)
    if title_match:
        new_title = title_match.group(1).strip()
        new_markdown = re.sub(r"^# .+$", f"# {new_title}", markdown, count=1, flags=re.MULTILINE)
        return EditResult(new_markdown, f'Title changed to "{new_title}".', applied=True)

    fr_match = _REMOVE_FR_RE.search(message)
    if fr_match:
        fr_id = f"FR-{fr_match.group(1)}"
        fr_line_re = re.compile(rf"^-\s*{re.escape(fr_id)}:", re.IGNORECASE)
        lines = markdown.splitlines()
        kept = [ln for ln in lines if not fr_line_re.match(ln)]
        if len(kept) == len(lines):
            return EditResult(markdown, f"Couldn't find {fr_id} in this PRD — nothing removed.", applied=False)
        return EditResult("\n".join(kept), f"Removed {fr_id}.", applied=True)

    if llm is not None:
        revised = revise_with_llm(llm, markdown, message)
        if revised.applied:
            return revised
        why = revised.reply
    else:
        why = "no model is available for rewrites in this mode (demo mode without LIVE_LLM)"

    note = f"- **Reviewer request (unresolved):** {message}"
    new_markdown = markdown.rstrip() + "\n" + note + "\n"
    reply = (
        f"I couldn't apply that rewrite — {why}. "
        "Added your request to Section 8 (Open Questions) as a flagged item instead of guessing. "
        "Renaming the title or removing a specific FR-N always works directly."
    )
    return EditResult(new_markdown, reply, applied=False)


def revise_with_llm(llm: LLMCall, markdown: str, instruction: str) -> EditResult:
    """One revision call. Returns applied=False with the reason on any failure;
    the caller decides what to do with the document then."""
    inputs = {"original_markdown": markdown, "instruction": instruction}
    try:
        out = llm({"edit_inputs": inputs})
    except Exception as exc:                                   # network, sphere FAILED, bad JSON
        logger.warning("prd-chat-edit call failed (%s)", exc)
        return EditResult(markdown, f"the model call failed ({type(exc).__name__})", applied=False)

    body = (out.get("prd_markdown") or "").strip()
    if len(body) < MIN_REVISION_CHARS:
        return EditResult(markdown, "the model returned an empty or truncated document", applied=False)

    invented = unsupported_numbers(body, inputs)
    if invented:
        logger.warning("prd revision cited ungrounded numbers %s — rejected", invented)
        return EditResult(markdown, f"the rewrite cited numbers that are not in the document: {invented}",
                          applied=False)

    body = _keep_banner(markdown, body)
    added, removed = _line_delta(markdown, body)
    model_reply = " ".join((out.get("reply") or "").split())
    reply = (model_reply or f"Applied: {instruction}.") + \
        f" ({added} line(s) added, {removed} removed; every number was already in the document; still a DRAFT.)"
    return EditResult(body, reply, applied=True)


def _keep_banner(original: str, revised: str) -> str:
    """The banner is ours, not the model's: if the rewrite dropped it, put the
    original banner back under the title (or at the top)."""
    if _BANNER_RE.search(revised):
        return revised
    banner = next((ln for ln in original.splitlines() if _BANNER_RE.match(ln)), None)
    if banner is None:
        return revised
    lines = revised.splitlines()
    if lines and lines[0].startswith("#"):
        return "\n".join([lines[0], "", banner, ""] + lines[1:])
    return "\n".join([banner, ""] + lines)


def _line_delta(before: str, after: str) -> tuple[int, int]:
    a = set(before.splitlines()); b = set(after.splitlines())
    return len(b - a), len(a - b)
