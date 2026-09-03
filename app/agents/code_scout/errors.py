"""Shared exception type for Code Scout's external dependencies (GitLab
search). Both LiveGitlabSearchClient and _live_search_fn (in
app/pipeline/nodes/code_scout.py) talk to real GitLab; before this, a
network error or non-2xx (requests.RequestException, surfaced via
raise_for_status()) or a malformed response body (a bare KeyError/ValueError
indexing into resp.json()) had nothing catching it anywhere up the call
chain. One flaky GitLab response during find_gap() OR during the Remedy
Loop's verify_remedy() would crash code_scout_node's entire run - not just
the repo or remedy it happened on.

Both call sites now wrap their requests calls and raise
CodeScoutExternalError so node.py / _run_remedies() can catch it at
repo/gap granularity and keep going with the rest of the run.
"""
from __future__ import annotations


class CodeScoutExternalError(Exception):
    """Raised when a call to GitLab (or another external dependency Code
    Scout talks to) fails, or returns an unexpected response shape."""
