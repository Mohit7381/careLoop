"""
Garuda communication-orchestration client. OWNER: Mohit.

REAL API (verified 2026-09-03 via org memory, traced from reminder-service's
send path) — this corrects the original planning artifact, which guessed
`/v3/communication_requests` with self-service `/v1/templates`. Neither
exists. The actual contract:

    POST {base_url}/v1/communication_requests?async=true
    Header: X-APP-TOKEN: <token>   (NOT "Authorization: Bearer ...")
    Body: {
      "destinations": [{"destination": ..., "template_id": ..., "channel_id": ..., "provider_id": ...}],
      "mode": "transactional",
      "data": {...},                 # must match the ${...} placeholders in the Garuda template exactly
      "async": true,
      "serviceSource": "careloop-service"
    }

Garuda resolves (channel_id, mode, provider_id) against its own
provider_routings config to pick an adapter — there is NO self-service
template registration. channel_id/provider_id/template_id must already
exist as real rows in Garuda; get them from whoever owns the Garuda
integration (same blocker Harshit flagged: webhook not received yet,
SRE not fully aware). OPEN QUESTION: every verified example is
WhatsApp/SMS/Email/Voice — confirm a GChat channel type actually exists
in Garuda before depending on this for the demo; if it doesn't, the team
needs a different GChat delivery path (e.g. a plain Chat webhook) instead
of routing through Garuda.

Per FR-04: delivery failure must NOT fail the run. Callers should catch
GarudaDeliveryError, log it, and continue — the report/PRD stays in run
artifacts either way.
"""
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger("careloop.garuda")


class GarudaDeliveryError(Exception):
    pass


def send_report(run_id: int, report_summary: str, report_link: str, prd_link: Optional[str] = None) -> None:
    """
    Sends the analysis report (and PRD link, if drafted) via Garuda. Retries
    once on failure, then raises GarudaDeliveryError for the caller to log
    and swallow — never let this fail the pipeline run.
    """
    settings = get_settings()
    required = [settings.garuda_base_url, settings.garuda_channel_id, settings.garuda_provider_id, settings.garuda_template_id, settings.garuda_destination]
    if not all(required):
        # Raise rather than silently return — callers (delivery_node,
        # POST /deliver) must be able to tell "actually sent" from "skipped,
        # not configured". A caller that wants a non-fatal skip catches
        # GarudaDeliveryError itself (delivery_node already does).
        raise GarudaDeliveryError(
            "Garuda not fully configured (base_url/channel_id/provider_id/template_id/destination) "
            "— see app/integrations/garuda_client.py for what's needed and confirm GChat is even a "
            "supported Garuda channel."
        )

    payload = {
        "destinations": [
            {
                "destination": settings.garuda_destination,
                "template_id": settings.garuda_template_id,
                "channel_id": settings.garuda_channel_id,
                "provider_id": settings.garuda_provider_id,
            }
        ],
        "mode": "transactional",
        "data": {
            "run_id": run_id,
            "summary": report_summary,
            "report_link": report_link,
            "prd_link": prd_link or "(no PRD drafted this run)",
        },
        "async": True,
        "serviceSource": settings.garuda_service_source,
    }

    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            resp = httpx.post(
                f"{settings.garuda_base_url}/v1/communication_requests",
                headers={"X-APP-TOKEN": settings.garuda_app_token},
                params={"async": "true"},
                json=payload,
                timeout=10,
            )
            if resp.status_code >= 400:
                raise GarudaDeliveryError(f"{resp.status_code} {resp.text}")
            return
        except Exception as exc:  # noqa: BLE001 - deliberately broad, delivery must never crash the run
            last_exc = exc
            logger.warning("Garuda delivery attempt %s failed for run %s: %s", attempt + 1, run_id, exc)

    raise GarudaDeliveryError(str(last_exc))
