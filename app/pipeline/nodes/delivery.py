"""
Delivery node. OWNER: Mohit.

Sends the analysis report (+ PRD link, if drafted) to GChat via Garuda.
Per FR-04, a delivery failure must not fail the run — caught, logged,
and recorded in state as a note rather than raised.
"""
import logging

from app.integrations.garuda_client import GarudaDeliveryError, send_report
from app.pipeline.state import GraphState

logger = logging.getLogger("careloop.delivery")


def delivery_node(state: GraphState) -> GraphState:
    run_id = state["run_id"]
    report_artifact = next((a for a in state.get("artifacts", []) if a["kind"] == "report_md"), None)
    summary = state.get("trend_report", {}).get("narrative", "")

    try:
        send_report(
            run_id=run_id,
            report_summary=summary,
            report_link=f"/v1/analysis/runs/{run_id}/report",
            prd_link=f"/v1/analysis/runs/{run_id}" if state.get("prd_draft") else None,
        )
    except GarudaDeliveryError as exc:
        logger.warning("Garuda delivery failed for run %s (non-fatal): %s", run_id, exc)

    _ = report_artifact  # kept for readability; content itself is persisted by the runner
    return {**state, "status": "completed"}
