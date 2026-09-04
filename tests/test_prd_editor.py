"""Chat-style PRD editing — narrow recognized intents + an honest fallback."""
from app.pipeline.prd_editor import apply_edit_instruction

SAMPLE = """# Fix: something\n\n## 5. Proposed Solution\n- FR-1: **[FR candidate]** do the first thing\n- FR-2: **[FR candidate]** do the second thing\n\n## 8. Open Questions\n- something to confirm\n"""


def test_title_rename():
    result = apply_edit_instruction(SAMPLE, "title: New Title Here")
    assert result.applied
    assert result.markdown.splitlines()[0] == "# New Title Here"


def test_remove_existing_fr():
    result = apply_edit_instruction(SAMPLE, "remove FR-2")
    assert result.applied
    assert "FR-2" not in result.markdown
    assert "FR-1" in result.markdown


def test_remove_missing_fr_is_honest_not_silent():
    result = apply_edit_instruction(SAMPLE, "delete FR-99")
    assert not result.applied
    assert "FR-99" in result.reply
    assert result.markdown == SAMPLE


def test_unrecognized_request_is_flagged_not_fabricated():
    result = apply_edit_instruction(SAMPLE, "make this more exciting")
    assert not result.applied
    assert "can't rewrite prose autonomously" in result.reply
    assert "make this more exciting" in result.markdown
