"""Replays are per journey, so a second journey never replays the first one's session."""
from pathlib import Path

from app.integrations.sphere import REPLAY_DIR, SphereClient, make_use_case_llm, replay_root_for


def test_pd_recording_lives_under_its_journey():
    assert (REPLAY_DIR / "pd_checkout" / "funnel-hypothesis-generation" / "0.json").exists()
    assert not (REPLAY_DIR / "funnel-hypothesis-generation").exists(), "legacy flat layout should be gone"


def test_replay_root_falls_back_when_a_journey_has_no_recordings(tmp_path):
    assert replay_root_for("pd_checkout") == REPLAY_DIR / "pd_checkout"
    assert replay_root_for("journey_that_does_not_exist") == REPLAY_DIR
    assert replay_root_for(None) == REPLAY_DIR


def test_factory_returns_none_for_a_journey_without_a_recording(monkeypatch):
    monkeypatch.setattr("app.integrations.sphere._live_llm_wanted", lambda demo: False)
    assert make_use_case_llm("funnel-hypothesis-generation", demo_mode=True, journey="pd_checkout") is not None
    assert make_use_case_llm("funnel-hypothesis-generation", demo_mode=True, journey="journey_that_does_not_exist") is None


def test_client_replays_from_the_given_root():
    c = SphereClient(mode="replay", replay_root=REPLAY_DIR / "pd_checkout")
    out = c.call("funnel-hypothesis-generation", 0, {"analysis_context": "{}"})
    assert "done" in out
