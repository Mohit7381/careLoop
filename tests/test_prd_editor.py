"""Chat-style PRD editing — narrow recognized intents, an LLM path for
everything else when one is wired in, and an honest fallback when it isn't
(or when its output can't be trusted)."""
from app.pipeline.prd_editor import apply_edit_instruction

SAMPLE = """# Fix: something\n\n## 5. Proposed Solution\n- FR-1: **[FR candidate]** do the first thing\n- FR-2: **[FR candidate]** do the second thing\n\n## 8. Open Questions\n- something to confirm\n"""
REWRITE = "# Fix: something\n\n" + "x" * 200 + "\n\n## 8. Open Questions\n- something to confirm\n"


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


def test_unrecognized_request_with_no_llm_is_flagged_not_fabricated():
    result = apply_edit_instruction(SAMPLE, "make this more exciting")
    assert not result.applied
    assert "no LLM is wired" in result.reply
    assert "make this more exciting" in result.markdown


def test_unrecognized_request_uses_the_llm_when_the_rewrite_is_grounded():
    def llm(inputs):
        assert inputs["instruction"] == "make this more exciting"
        assert inputs["original_markdown"] == SAMPLE
        return {"prd_markdown": REWRITE, "reply": "Reworded the summary."}

    result = apply_edit_instruction(SAMPLE, "make this more exciting", llm=llm)
    assert result.applied
    assert result.markdown == REWRITE.strip()
    assert result.reply == "Reworded the summary."


def test_llm_rewrite_that_is_too_short_falls_back_honestly():
    result = apply_edit_instruction(SAMPLE, "make this more exciting",
                                     llm=lambda inputs: {"prd_markdown": "too short"})
    assert not result.applied
    assert "too short to trust" in result.reply
    assert "make this more exciting" in result.markdown


def test_llm_rewrite_with_invented_numbers_falls_back_honestly():
    ungrounded = REWRITE + "\nWe expect this to recover 84213 orders per day.\n"
    result = apply_edit_instruction(SAMPLE, "add a number",
                                     llm=lambda inputs: {"prd_markdown": ungrounded})
    assert not result.applied
    assert "numbers not present" in result.reply


def test_llm_rewrite_with_corrupted_control_bytes_falls_back_honestly():
    """A live call was observed returning prose where em dashes / middle dots
    / stars had been replaced by stray control bytes — must not ship that
    just because it's long enough and cites no invented numbers."""
    corrupted = REWRITE[:-1] + " and a corrupted byte: \x14 right there.\n"
    result = apply_edit_instruction(SAMPLE, "make this more exciting",
                                     llm=lambda inputs: {"prd_markdown": corrupted})
    assert not result.applied
    assert "corrupted characters" in result.reply


def test_llm_call_failure_falls_back_honestly_instead_of_raising():
    def broken_llm(inputs):
        raise RuntimeError("sphere is down")

    result = apply_edit_instruction(SAMPLE, "make this more exciting", llm=broken_llm)
    assert not result.applied
    assert "edit request failed" in result.reply


def test_recognized_intents_take_the_fast_path_even_when_an_llm_is_wired():
    def exploding_llm(inputs):
        raise AssertionError("should not be called for a recognized intent")

    result = apply_edit_instruction(SAMPLE, "title: New Title Here", llm=exploding_llm)
    assert result.applied
    assert result.markdown.splitlines()[0] == "# New Title Here"
