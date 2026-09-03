"""LiveGitlabSearchClient - resilience + path-filtering coverage (PR #3 review).

Before this, requests.RequestException / a non-2xx / a malformed response
body had nothing catching them, so a single bad GitLab call crashed
code_scout_node's whole run; and find_gap() took hits[0] unfiltered, so a
search term could resolve to a markdown doc or a *Test.java file instead of
real source.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.search_client import LiveGitlabSearchClient, is_source_path


def _client() -> LiveGitlabSearchClient:
    return LiveGitlabSearchClient(host="https://gitlab.test", token="tok")


def test_is_source_path_accepts_real_source():
    assert is_source_path("src/main/java/com/halodoc/timor/oms/OrderDao.java") is True


def test_is_source_path_rejects_docs_and_tests():
    assert is_source_path("AGENTS.md") is False
    assert is_source_path("context/database_schema.md") is False
    assert is_source_path("src/test/java/com/halodoc/timor/oms/OrderDaoTest.java") is False


@patch("app.agents.code_scout.search_client.requests.get")
def test_project_id_wraps_a_network_failure(mock_get):
    mock_get.side_effect = requests.ConnectionError("connection refused")
    with pytest.raises(CodeScoutExternalError):
        _client()._project_id("bintan/consultation")


@patch("app.agents.code_scout.search_client.requests.get")
def test_project_id_wraps_a_non_2xx_response(mock_get):
    resp = MagicMock(status_code=404)
    resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    mock_get.return_value = resp
    with pytest.raises(CodeScoutExternalError):
        _client()._project_id("bintan/consultation")


@patch("app.agents.code_scout.search_client.requests.get")
def test_project_id_wraps_a_malformed_response_body(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"no_id_here": True})
    with pytest.raises(CodeScoutExternalError):
        _client()._project_id("bintan/consultation")


@patch("app.agents.code_scout.search_client.requests.get")
def test_find_gap_skips_a_failing_search_term_but_keeps_the_others(mock_get):
    """One bad search term must not abort the whole find_gap() call - later
    terms still get a chance."""
    project_resp = MagicMock(status_code=200, json=lambda: {"id": 42})
    failing_search = requests.ConnectionError("timeout")
    ok_search = MagicMock(
        status_code=200,
        json=lambda: [{"path": "OrderDao.java", "ref": "master"}],
    )
    raw_file_resp = MagicMock(status_code=200, text="line1\nabandon call here\nline3")

    mock_get.side_effect = [project_resp, failing_search, ok_search, raw_file_resp]

    client = _client()
    location, searches_run = client.find_gap(1, "timor/oms", ["garuda", "abandon"])

    assert searches_run == 2
    assert location is not None
    assert location.file == "OrderDao.java"
    assert location.line == 2


@patch("app.agents.code_scout.search_client.requests.get")
def test_find_gap_skips_a_doc_hit_and_finds_the_real_source_hit(mock_get):
    """review D1: an unfiltered hits[0] used to resolve to a doc file - now
    find_gap() scans past it for the first real source hit."""
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
    location, searches_run = client.find_gap(1, "timor/oms", ["confirmed"])

    assert location is not None
    assert location.file == "src/main/java/com/halodoc/timor/oms/OrderDao.java"
