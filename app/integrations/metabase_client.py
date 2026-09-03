"""
Read-only Metabase API client. OWNER: Alief.

v1's single data dependency (verified 2026-09-02 live via the de-central
Metabase proxy, Redshift DB 39) — no direct prod MySQL credentials needed.

Primary: monetization.modeled_fact_consultation_transaction
Secondary: monetization.modeled_fact_pharmacy_transaction_delivery,
           monetization_dwh.modeled_fact_halodoc_consumer_event (aggregates only — raw PII columns present)
Drill-down/validation only: bintan_consultation.*, oms.orders / oms.order_attributes

NOT YET IMPLEMENTED. This is the seam app/pipeline/nodes/fetcher.py calls
into once demo_mode=False. Keep queries chunked <60s, apply k>=25
suppression before returning, and never let a raw PII column leave this
module.
"""
from typing import Any

from app.config import get_settings


class MetabaseClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def run_card(self, card_id: int, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError("Alief: wire this to the de-central Metabase proxy / card API")

    def run_query_pack(self, window_start: str, window_end: str) -> dict[str, Any]:
        """Should return the same shape app/pipeline/nodes/fetcher.py builds from fixtures."""
        raise NotImplementedError("Alief: run the frozen query pack for [window_start, window_end]")
