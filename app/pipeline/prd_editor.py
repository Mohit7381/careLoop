"""
Chat-style PRD editing. OWNER: Mohit.

A human reviewing a DRAFT PRD can ask for a change in plain language
instead of hand-editing markdown. This is intentionally narrow rather than
a free-form rewrite: it recognizes a small set of concrete, safe edits it
can actually perform, and for anything else it's honest that it can't
apply the change autonomously yet (same "insufficient capability is a
valid output, don't fabricate" discipline used everywhere else in this
pipeline) — rather than pretending an LLM rewrote the document when none
is wired up. Swap the fallback branch for a real sphere-platform call
(use case: settings.llm_use_case_prd_generation, a revision mode) when
ready; keep the recognized-intent branches as fast paths regardless,
since they're free and don't need a network call.

Recognized intents:
  - "title: <new title>" / "rename title to <new title>" -> renames the H1
  - "remove FR-<n>" / "delete FR-<n>" -> drops that functional requirement row
  - anything else -> appended to Open Questions as a human-flagged note,
    not silently dropped and not silently "fixed"
"""
import re
from dataclasses import dataclass


@dataclass
class EditResult:
    markdown: str
    reply: str
    applied: bool


_TITLE_RE = re.compile(r"^(?:title:\s*|rename title to\s+)(.+)$", re.IGNORECASE)
_REMOVE_FR_RE = re.compile(r"\b(?:remove|delete)\s+fr[-\s]?(\d+)\b", re.IGNORECASE)


def apply_edit_instruction(markdown: str, message: str) -> EditResult:
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

    note = f"- **Reviewer request (unresolved):** {message}"
    new_markdown = markdown.rstrip() + "\n" + note + "\n"
    reply = (
        "I can't rewrite prose autonomously yet — no LLM is wired into this edit path "
        "(same seam as the PRD generator's own TODO for a real sphere-platform call). "
        "Added your request to Section 8 (Open Questions) as a flagged item instead of "
        "guessing at a rewrite. I can rename the title or remove a specific FR-N directly — "
        "try one of those if that's what you need."
    )
    return EditResult(new_markdown, reply, applied=False)
