"""SphereClient._live() — create-then-poll instead of one blocking call.

An ingress gateway in front of sphere cuts a held-open connection at ~60s
even when sphere itself is still working (a live call was observed
returning HTTP 504 at 60s and SUCCESS at 74s — see semantic_voc.py, and
the same ~60s cutoff was observed independently against sphere's own
/v2/chat-ai/requests by another org caller). Polling on a short interval
means no single HTTP call is ever exposed to that cutoff, even though the
overall wait can legitimately stretch past it.

Mocks urllib.request.urlopen directly (not `requests`) since SphereClient
is the one sphere caller still on urllib.
"""
import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from app.integrations import sphere
from app.integrations.sphere import SphereClient, SphereRequestFailed, SphereRequestTimedOut


def _response(body: dict) -> MagicMock:
    r = MagicMock()
    r.read.return_value = json.dumps(body).encode()
    r.__enter__ = lambda self: r
    r.__exit__ = lambda self, *a: False
    return r


def _client() -> SphereClient:
    return SphereClient(mode="sphere", service_type="funnel-analysis")


@patch("app.integrations.sphere.urllib.request.urlopen")
def test_success_on_the_create_call_itself_never_polls(mock_urlopen):
    mock_urlopen.return_value = _response({"status": "SUCCESS", "data": {"ok": True}})

    out = _client().call("prd-generation", 21691, {"prd_inputs": "{}"})

    assert out == {"ok": True}
    assert mock_urlopen.call_count == 1  # no poll call needed


@patch("app.integrations.sphere.time.sleep")  # no real waiting in the test
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_polls_until_success(mock_urlopen, mock_sleep):
    mock_urlopen.side_effect = [
        _response({"status": "PENDING", "request_id": "r1"}),  # create
        _response({"status": "PENDING"}),                      # poll 1
        _response({"status": "IN_PROGRESS"}),                  # poll 2 — unknown-but-not-terminal
        _response({"status": "SUCCESS", "data": {"ok": True}}),  # poll 3
    ]

    out = _client().call("prd-generation", 21691, {"prd_inputs": "{}"})

    assert out == {"ok": True}
    assert mock_urlopen.call_count == 4
    # the poll calls hit GET /v1/chat-ai/requests/{request_id}
    poll_urls = [c.args[0].full_url for c in mock_urlopen.call_args_list[1:]]
    assert all(url.endswith("/v1/chat-ai/requests/r1") for url in poll_urls)


@patch("app.integrations.sphere.time.sleep")
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_poll_calls_use_a_short_timeout_not_one_long_one(mock_urlopen, mock_sleep):
    """The whole point of polling: no single POLL call should be held open
    long enough to hit the ~60s ingress cutoff, even though polling overall
    can run well past 60s. The CREATE call is exempt — for a synchronous use
    case it IS the LLM call and has to wait for it (see CREATE_TIMEOUT_S)."""
    mock_urlopen.side_effect = [
        _response({"status": "PENDING", "request_id": "r1"}),
        _response({"status": "SUCCESS", "data": {}}),
    ]

    _client().call("prd-generation", 21691, {"prd_inputs": "{}"})

    poll_calls = mock_urlopen.call_args_list[1:]
    assert poll_calls, "expected at least one poll call"
    for call in poll_calls:
        assert call.kwargs["timeout"] <= 15


@patch("app.integrations.sphere.time.sleep")
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_terminal_failure_status_raises_without_exhausting_the_poll_budget(mock_urlopen, mock_sleep):
    mock_urlopen.side_effect = [
        _response({"status": "PENDING", "request_id": "r1"}),
        _response({"status": "FAILED", "comments": "template render error"}),
    ]

    with pytest.raises(SphereRequestFailed):
        _client().call("prd-generation", 21691, {"prd_inputs": "{}"})

    assert mock_urlopen.call_count == 2  # stopped at the failure, did not keep polling


@patch("app.integrations.sphere.time.monotonic")
@patch("app.integrations.sphere.time.sleep")
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_gives_up_honestly_after_max_poll_seconds_on_an_unrecognised_status(mock_urlopen, mock_sleep, mock_monotonic):
    """Sphere's exact pending-status vocabulary isn't confirmed, so an
    unrecognised non-SUCCESS status must never be silently treated as
    success or hang forever — it polls to the deadline, then raises."""
    mock_urlopen.side_effect = [
        _response({"status": "PENDING", "request_id": "r1"}),
        _response({"status": "SOME_UNKNOWN_STATUS"}),
        _response({"status": "SOME_UNKNOWN_STATUS"}),
    ]
    # monotonic(): one call for the deadline, then advances past it on the 2nd check
    mock_monotonic.side_effect = [0, 1, 200]

    with pytest.raises(SphereRequestTimedOut):
        _client().call("prd-generation", 21691, {"prd_inputs": "{}"})


@patch("app.integrations.sphere.urllib.request.urlopen")
def test_no_request_id_and_no_terminal_status_fails_honestly_instead_of_guessing(mock_urlopen):
    mock_urlopen.return_value = _response({"status": "PENDING"})  # no request_id to poll

    with pytest.raises(SphereRequestFailed, match="neither a terminal status nor a request_id"):
        _client().call("prd-generation", 21691, {"prd_inputs": "{}"})
