"""
sphere-platform LLM gateway client.

Real request contract, confirmed 2026-09-03 via a live working curl
(Krithik, for a different use case — item_diagnosis_mapping /
sphere-insurance — but the endpoint/header/body SHAPE is shared across
all use cases):

    POST {base_url}/v1/chat-ai/requests
    Header: X-App-Token: <token>
    Body: {
      "use_case": "<use case name from AI Studio>",
      "service_type": "<project/service identifier>",
      "params": { ...use-case-specific fields... }
    }

Any `params` value that's naturally an object or array is sent as a
JSON-ENCODED STRING, not nested JSON (matches the insurance example:
item_details, clinical_context, secondary_diagnoses, patient_demographics
were all stringified). `call_use_case` below does that encoding for you —
pass plain Python dicts/lists and it stringifies whatever needs it.

CONFIRMED 2026-09-03 (queried AI Studio's own API directly, GET
/api/v1/ai-studio/projects/7121/use-cases/search): service_type is
"funnel-analysis" for all 5 use cases — matches the project name exactly.

STILL OPEN (confirm with Nakul, who set up AI Studio project 7121):
  - `sphere_platform_app_token` — need our own, scoped to project 7121;
    the example curl's token belongs to a different project entirely
    (item_diagnosis_mapping / sphere-insurance) and won't authorize ours.
  - The exact `params` field NAMES each of our 5 use cases expects — and
    this is now a bigger gap than "I couldn't find the editor": querying
    the use-case API directly shows `param_definition: null` and
    `json_schema: null` on every one of the 5 use cases. The project/
    use-case SHELLS exist (created by "SYSTEM"), but no one has actually
    authored the prompt template body / input schema / output schema yet.
    There is nothing to call yet, regardless of token — this needs
    Nakul (or whoever owns AI Studio setup) to actually write the 5
    prompt templates before any real integration can happen.
"""
import json
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("careloop.sphere_platform")


class SpherePlatformError(Exception):
    pass


def _stringify_complex_values(params: dict[str, Any]) -> dict[str, Any]:
    return {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}


def call_use_case(use_case: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    """
    Calls one sphere-platform use case and returns the parsed JSON response.
    Raises SpherePlatformError on any non-2xx or transport failure — callers
    (the pipeline nodes) decide whether that's fatal or falls back to a stub.
    """
    settings = get_settings()
    if not settings.sphere_platform_app_token or not settings.sphere_platform_service_type:
        raise SpherePlatformError(
            "sphere-platform not configured (SPHERE_PLATFORM_APP_TOKEN / SPHERE_PLATFORM_SERVICE_TYPE) "
            "— see app/config.py for what's still open"
        )

    payload = {
        "use_case": use_case,
        "service_type": settings.sphere_platform_service_type,
        "params": _stringify_complex_values(params),
    }

    try:
        resp = httpx.post(
            f"{settings.sphere_platform_base_url}/v1/chat-ai/requests",
            headers={"X-App-Token": settings.sphere_platform_app_token, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        raise SpherePlatformError(f"{exc.response.status_code} {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise SpherePlatformError(str(exc)) from exc
