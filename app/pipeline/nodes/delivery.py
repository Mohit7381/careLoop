"""
Finalize node (was: auto-delivery). OWNER: Mohit.

Per the plan (rev 2.1, demo beat 8) and confirmed live: "never auto-filed"
and "a human clicking Approve is what makes it real" — a run finishing
must NOT push to GChat by itself. This node used to call Garuda
unconditionally as the pipeline's last step, so a message went out before
any human had seen the draft, and it made POST /v1/analysis/runs/{id}/deliver
(the actual Approve action) redundant/inconsistent with it. Caught in
frontend verification (Pritom) — real bug, not stale.

Delivery now happens ONLY via the explicit POST .../deliver endpoint,
which a human triggers by clicking Approve in the UI. This node just
marks the run's terminal status.
"""
from app.pipeline.state import GraphState


def delivery_node(state: GraphState) -> GraphState:
    return {**state, "status": "completed"}
