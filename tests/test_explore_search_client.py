"""LiveGitlabExploreSearchClient - failure-path + path-filtering coverage.

Without this, requests.RequestException (network errors, non-2xx via
raise_for_status()) and malformed-response KeyErrors had nothing catching
them, so a single bad GitLab call would crash the whole suggestion node's
run. These tests prove the client instead raises CodeScoutExternalError,
which suggestion_node.py can (and does) catch per finding/repo.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.explore_search_client import LiveGitlabExploreSearchClient


def _client() -> LiveGitlabExploreSearchClient:
    return LiveGitlabExploreSearchClient(host="https://gitlab.test", token="tok")


@patch("app.agents.code_scout.explore_search_client.requests.get")
def test_project_id_wraps_a_network_failure(mock_get):
    mock_get.side_effect = requests.ConnectionError("connection refused")
    with pytest.raises(CodeScoutExternalError):
        _client()._project_id("bintan/consultation")


@patch("app.agents.code_scout.explore_search_client.requests.get")
def test_project_id_wraps_a_non_2xx_response(mock_get):
    resp = MagicMock(status_code=404)
    resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    mock_get.return_value = resp
    with pytest.raises(CodeScoutExternalError):
        _client()._project_id("bintan/consultation")


@patch("app.agents.code_scout.explore_search_client.requests.get")
def test_project_id_wraps_a_malformed_response_body(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"no_id_here": True})
    with pytest.raises(CodeScoutExternalError):
        _client()._project_id("bintan/consultation")


@patch("app.agents.code_scout.explore_search_client.requests.get")
def test_explore_recovers_when_the_project_lookup_fails(mock_get):
    """explore() has nothing to search without a resolved project id, so it
    still raises for the caller (suggestion_node.py) to catch at the repo
    level - but it must be CodeScoutExternalError, not a raw exception."""
    mock_get.side_effect = requests.ConnectionError("connection refused")
    with pytest.raises(CodeScoutExternalError):
        _client().explore(1, "bintan/consultation", ["garuda"], budget=8)


@patch("app.agents.code_scout.explore_search_client.requests.get")
def test_explore_skips_a_failing_search_term_but_keeps_the_others(mock_get):
    """One bad search term must not abort the whole exploration - later
    terms still get a chance."""
    project_resp = MagicMock(status_code=200, json=lambda: {"id": 42})
    failing_search = requests.ConnectionError("timeout")
    ok_search = MagicMock(
        status_code=200,
        json=lambda: [{"path": "ConsultationDao.java", "ref": "master"}],
    )
    raw_file_resp = MagicMock(status_code=200, text="line1\nabandon call here\nline3")

    mock_get.side_effect = [
        project_resp,  # _project_id
        failing_search,  # term 1: "garuda" search fails
        ok_search,  # term 2: "abandon" search succeeds
        raw_file_resp,  # _resolve_exact_location's raw fetch for term 2's hit
    ]

    client = _client()
    inventory, searches_run = client.explore(1, "bintan/consultation", ["garuda", "abandon"], budget=8)

    assert searches_run == 2
    assert len(inventory) == 1
    assert inventory[0].file == "ConsultationDao.java"
    assert inventory[0].line == 2


@patch("app.agents.code_scout.explore_search_client.requests.get")
def test_explore_skips_a_doc_hit_and_finds_the_real_source_hit(mock_get):
    """review D1.1: an unfiltered search used to be able to resolve to a doc
    file - explore() now scans past it for the first real source hit."""
    project_resp = MagicMock(status_code=200, json=lambda: {"id": 61})
    search_resp = MagicMock(
        status_code=200,
        json=lambda: [
            {"path": "context/database_schema.md", "ref": "master"},
            {"path": "AGENTS.md", "ref": "master"},
            {"path": "src/main/java/com/halodoc/timor/oms/OrderDao.java", "ref": "master"},
        ],
    )
    raw_file_resp = MagicMock(status_code=200, text="line1\nconfirmed order here\nline3")

    mock_get.side_effect = [project_resp, search_resp, raw_file_resp]

    client = _client()
    inventory, _ = client.explore(1, "timor/oms", ["confirmed"], budget=8)

    assert len(inventory) == 1
    assert inventory[0].file == "src/main/java/com/halodoc/timor/oms/OrderDao.java"
