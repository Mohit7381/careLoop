"""
Chat-style PRD editing. OWNER: Mohit.

A human reviewing a DRAFT PRD can ask for a change in plain language
instead of hand-editing markdown. The two recognized-intent branches below
(title rename, remove FR-N) are always tried first regardless of whether an
LLM is wired in — they're free, deterministic, and don't need a network
call. Anything else goes through the `prd-chat-edit` sphere use case when
one is passed in; when it isn't (no template provisioned yet, or the call
fails, or the response doesn't survive the same grounding check the PRD
generator itself uses), it's honest that it can't apply the change
autonomously rather than pretending a rewrite happened — same
"insufficient capability is a valid output, don't fabricate" discipline
used everywhere else in this pipeline.

Recognized intents:
  - "title: <new title>" / "rename title to <new title>" -> renames the H1
  - "remove FR-<n>" / "delete FR-<n>" -> drops that functional requirement row
  - anything else -> tried against the LLM if one is wired in; on any
    failure, appended to Open Questions as a human-flagged note instead of
    being silently dropped or silently "fixed"
"""
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.agents.evidence_gate import unsupported_numbers

logger = logging.getLogger(__name__)

LLMCall = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class EditResult:
    markdown: str
    reply: str
    applied: bool


_TITLE_RE = re.compile(r"^(?:title:\s*|rename title to\s+)(.+)$", re.IGNORECASE)
_REMOVE_FR_RE = re.compile(r"\b(?:remove|delete)\s+fr[-\s]?(\d+)\b", re.IGNORECASE)
# A live call returned prose where every em dash / middle dot / star / plus-minus sign had
# been replaced by a single control byte (e.g. em-dash "—" -> "\x14") — reproduced against the
# real prd-chat-edit endpoint 2026-09-04, not a local encoding bug (this repo's own read/write
# round-trips UTF-8 correctly; confirmed by direct test). Cause not confirmed (sphere-side
# guardrail or transport), but the fix has to live here regardless: never ship visibly-corrupted
# prose just because the length/number checks below don't catch it.
_BAD_CONTROL_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_FALLBACK_REPLY = (
    "I can't apply that change autonomously — {reason}. Added your request to "
    "Section 8 (Open Questions) as a flagged item instead of guessing at a "
    "rewrite. I can rename the title or remove a specific FR-N directly — "
    "try one of those if that's what you need."
)


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

    reason = "no LLM is wired into this edit path"
    if llm is not None:
        result, reason = _apply_via_llm(markdown, message, llm)
        if result is not None:
            return result

    note = f"- **Reviewer request (unresolved):** {message}"
    new_markdown = markdown.rstrip() + "\n" + note + "\n"
    return EditResult(new_markdown, _FALLBACK_REPLY.format(reason=reason), applied=False)


def _apply_via_llm(markdown: str, message: str, llm: LLMCall) -> tuple[Optional[EditResult], str]:
    """Returns (result, reason). result is None when the caller should fall
    back to the honest Open-Questions note; `reason` says why, for the reply."""
    inputs = {"original_markdown": markdown, "instruction": message}
    try:
        out = llm(inputs)
    except Exception as exc:
        logger.warning("prd-chat-edit call failed (%s) — honest fallback", exc)
        return None, "the edit request failed"

    new_markdown = (out.get("prd_markdown") or "").strip()
    if len(new_markdown) < 200:
        logger.warning("prd-chat-edit returned %d chars — honest fallback", len(new_markdown))
        return None, "the rewrite came back too short to trust"

    bad_chars = set(_BAD_CONTROL_CHARS.findall(new_markdown)) - set(_BAD_CONTROL_CHARS.findall(markdown))
    if bad_chars:
        logger.warning("prd-chat-edit returned corrupted control bytes %s — honest fallback",
                        [hex(ord(c)) for c in bad_chars])
        return None, "the rewrite came back with corrupted characters"

    invented = unsupported_numbers(new_markdown, inputs)
    if invented:
        logger.warning("prd-chat-edit cited ungrounded numbers %s — honest fallback", invented)
        return None, "the rewrite cited numbers not present in the PRD or your message"

    reply = (out.get("reply") or "").strip() or "Updated the PRD per your request."
    return EditResult(new_markdown, reply, applied=True), ""
