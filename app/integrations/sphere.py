"""Thin sphere-platform client with a replay mode.

Modes (env LLM_MODE): "sphere" (live, stage) | "replay" (fixtures/llm_replay).
The Analyst receives this via injection, so tests use StubLLM instead.
Project/template ids: fixtures/pd_checkout/funnel_analysis_ids.json.
"""
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Optional

SPHERE_BASE = os.environ.get("SPHERE_BASE_URL", "http://sphere-platform.stage-k8s.halodoc.com")
def _app_token() -> str:
    """Shell env wins; otherwise the .env-backed settings.

    Three names had grown for one secret (SPHERE_APP_TOKEN in the shell,
    sphere_platform_app_token in settings, SPHERE_PLATFORM_API_KEY in
    .env.example) and a module-level read of only the first meant a token
    placed in .env never reached this client. Resolved lazily so the API
    server picks it up from .env without an exported shell variable.
    """
    tok = os.environ.get("SPHERE_APP_TOKEN", "")
    if tok:
        return tok
    from app.config import get_settings  # local import: config must not import us
    return get_settings().sphere_platform_app_token or ""


def _live_llm_wanted(demo_mode: bool) -> bool:
    from app.config import get_settings
    return (not demo_mode) or bool(get_settings().live_llm)
REPLAY_DIR = Path(os.environ.get("LLM_REPLAY_DIR", "fixtures/llm_replay"))


class SphereClient:
    def __init__(self, mode: Optional[str] = None, service_type: str = "funnel-analysis"):
        self.mode = mode or os.environ.get("LLM_MODE", "sphere")
        self.service_type = service_type
        self._replay_counters: dict[str, int] = {}

    def call(self, use_case: str, template_id: int, params: dict[str, str]) -> dict[str, Any]:
        if self.mode == "replay":
            return self._replay(use_case)
        return self._live(use_case, template_id, params)

    def _live(self, use_case: str, template_id: int, params: dict[str, str]) -> dict[str, Any]:
        body = {
            "service_type": self.service_type,
            "use_case": use_case,
            "template_id": template_id,  # required — output_schema is not applied without it
            "params": params,
        }
        req = urllib.request.Request(
            f"{SPHERE_BASE}/v1/chat-ai/requests/validation",
            method="POST",
            headers={"X-APP-TOKEN": _app_token(), "Content-Type": "application/json"},
            data=json.dumps(body).encode(),
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.loads(r.read())
        if resp.get("status") != "SUCCESS":
            raise RuntimeError(f"sphere call failed for {use_case}: {str(resp)[:300]}")
        return resp.get("data") or {}

    def _replay(self, use_case: str) -> dict[str, Any]:
        """Sequential replay: fixtures/llm_replay/<use_case>/<n>.json per call."""
        n = self._replay_counters.get(use_case, 0)
        self._replay_counters[use_case] = n + 1
        path = REPLAY_DIR / use_case / f"{n}.json"
        if not path.exists():  # exhausted -> last recorded response, or hard fail
            last = sorted((REPLAY_DIR / use_case).glob("*.json"))
            if not last:
                raise FileNotFoundError(f"no replay fixtures for {use_case} under {REPLAY_DIR}")
            path = last[-1]
        return json.loads(path.read_text())


SPHERE_IDS_PATH = Path("fixtures/pd_checkout/sphere_ids.json")


def make_use_case_llm(use_case: str, demo_mode: bool):
    """An `llm(ctx) -> dict` for one sphere use case, or None if unavailable.

    Returning None rather than raising is deliberate: the Reporter and the PRD
    generator both fall back to their deterministic renderers, and a missing
    replay fixture or an unset token should degrade the prose, never fail the
    run. Demo mode replays a recorded session; live mode calls sphere.
    """
    try:
        ids = json.loads(SPHERE_IDS_PATH.read_text())
        template_id = next(u["template_id"] for u in ids["use_cases"]
                           if u["name"] == use_case)
    except Exception:
        return None

    if _live_llm_wanted(demo_mode):
        if not _app_token():
            return None
        client = SphereClient(mode="sphere")
    else:
        if not (Path("fixtures/llm_replay") / use_case).exists():
            return None                      # nothing recorded yet
        client = SphereClient(mode="replay")

    def llm(ctx: dict[str, Any]) -> dict[str, Any]:
        params = {k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
                  for k, v in ctx.items()}
        return client.call(use_case, template_id, params)

    return llm
