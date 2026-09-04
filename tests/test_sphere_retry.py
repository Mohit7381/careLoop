"""One retry on a transient failure of the (synchronous) create call. Runs 30
and 37 failed on their first Analyst turn because a single call crossed the
~60 s ingress limit (HTTP 504); the same call succeeded on the next run."""
import io
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.integrations import sphere


def _http_error(code):
    return urllib.error.HTTPError("http://sphere/v1/chat-ai/requests", code, "err", {}, io.BytesIO(b"{}"))


def _ok(data):
    m = MagicMock()
    m.__enter__.return_value.read.return_value = __import__("json").dumps({"status": "SUCCESS", "data": data}).encode()
    return m


def _client():
    return sphere.SphereClient(mode="sphere")


@patch("app.integrations.sphere.time.sleep")
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_a_gateway_cut_is_retried_once_and_the_retry_wins(mock_urlopen, mock_sleep):
    mock_urlopen.side_effect = [_http_error(504), _ok({"done": True, "findings": []})]
    out = _client().call("prd-generation", 21691, {"prd_inputs": "{}"})
    assert out == {"done": True, "findings": []}
    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once_with(sphere.RETRY_PAUSE_S)


@patch("app.integrations.sphere.time.sleep")
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_two_gateway_cuts_fail_the_call(mock_urlopen, mock_sleep):
    mock_urlopen.side_effect = [_http_error(504), _http_error(504)]
    with pytest.raises(sphere.SphereRequestFailed) as exc:
        _client().call("prd-generation", 21691, {"prd_inputs": "{}"})
    assert exc.value.status == 504
    assert mock_urlopen.call_count == 2                 # exactly one retry, never a loop


@patch("app.integrations.sphere.time.sleep")
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_a_client_error_is_not_retried(mock_urlopen, mock_sleep):
    mock_urlopen.side_effect = [_http_error(422)]
    with pytest.raises(sphere.SphereRequestFailed) as exc:
        _client().call("prd-generation", 21691, {"prd_inputs": "{}"})
    assert exc.value.status == 422
    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


@patch("app.integrations.sphere.time.sleep")
@patch("app.integrations.sphere.urllib.request.urlopen")
def test_a_connection_error_counts_as_transient(mock_urlopen, mock_sleep):
    mock_urlopen.side_effect = [urllib.error.URLError("nodename nor servname provided"), _ok({"x": 1})]
    assert _client().call("prd-generation", 21691, {"prd_inputs": "{}"}) == {"x": 1}
