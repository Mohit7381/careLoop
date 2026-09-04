"""app/agents/code_scout/commit_history_client.py — GitLab blame walking."""
from unittest.mock import MagicMock, patch

from app.agents.code_scout.commit_history_client import LiveGitlabCommitHistoryClient


def _blame_response():
    return [
        {"commit": {"id": "aaa111", "author_name": "old-author",
                    "committed_date": "2026-01-01T00:00:00Z", "message": "old hunk"},
         "lines": ["line 1", "line 2"]},
        {"commit": {"id": "bbb222", "author_name": "new-author",
                    "committed_date": "2026-08-20T00:00:00Z", "message": "the fix\nmore detail"},
         "lines": ["line 3", "line 4", "line 5"]},
    ]


@patch("app.agents.code_scout.commit_history_client.requests.get")
def test_blame_line_walks_hunks_to_find_the_right_commit(mock_get):
    project_resp = MagicMock(status_code=200, json=lambda: {"id": 99})
    blame_resp = MagicMock(status_code=200, json=_blame_response)
    mock_get.side_effect = [project_resp, blame_resp]

    client = LiveGitlabCommitHistoryClient(host="https://gitlab.example.com", token="tok")
    commit = client.blame_line("timor/oms", "Retention.java", 4)  # falls in the second hunk (lines 3-5)

    assert commit is not None
    assert commit.sha == "bbb222"
    assert commit.author == "new-author"
    assert commit.date == "2026-08-20T00:00:00Z"
    assert commit.message == "the fix"  # first line only
    assert commit.web_url == "https://gitlab.example.com/timor/oms/-/commit/bbb222"


@patch("app.agents.code_scout.commit_history_client.requests.get")
def test_blame_line_returns_none_past_the_end_of_the_file(mock_get):
    project_resp = MagicMock(status_code=200, json=lambda: {"id": 99})
    blame_resp = MagicMock(status_code=200, json=_blame_response)
    mock_get.side_effect = [project_resp, blame_resp]

    client = LiveGitlabCommitHistoryClient(host="https://gitlab.example.com", token="tok")
    commit = client.blame_line("timor/oms", "Retention.java", 999)

    assert commit is None


@patch("app.agents.code_scout.commit_history_client.requests.get")
def test_blame_line_never_raises_on_a_network_failure(mock_get):
    import requests
    mock_get.side_effect = requests.ConnectionError("refused")

    client = LiveGitlabCommitHistoryClient(host="https://gitlab.example.com", token="tok")
    commit = client.blame_line("timor/oms", "Retention.java", 1)

    assert commit is None
