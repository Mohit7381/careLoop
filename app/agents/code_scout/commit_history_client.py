"""GitLab blame-backed commit attribution for the closed-loop impact feature
(app.agents.code_scout.impact). Mirrors search_client.py's two-implementation
shape: FixtureCommitHistoryClient for demo mode, LiveGitlabCommitHistoryClient
for the real GitLab blame API — never crashes the run, matching this
package's existing resilience discipline (a failed lookup is just "not
detected as shipped", not an error).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional
from urllib.parse import quote

import requests

from app.schemas.contracts import ShippedCommit

logger = logging.getLogger(__name__)


class FixtureCommitHistoryClient:
    """Demo mode. Keyed by (repo, file, line); returns a canned commit whose
    date is computed relative to today (not a frozen calendar date) so the
    scripted example stays "recent" — and therefore still demoable — no
    matter when the demo is actually run, unlike the rest of this repo's
    frozen-window fixtures (which represent historical business data and are
    deliberately static)."""

    def __init__(self, commits: Optional[dict[tuple[str, str, int], ShippedCommit]] = None):
        self._commits = commits or {}

    def blame_line(self, repo: str, file: str, line: int) -> Optional[ShippedCommit]:
        return self._commits.get((repo, file, line))


def scripted_commit(days_ago: int, sha: str, author: str, message: str,
                    web_url: Optional[str] = None) -> ShippedCommit:
    commit_date = (date.today() - timedelta(days=days_ago)).isoformat()
    return ShippedCommit(sha=sha, short_sha=sha[:8], author=author, date=commit_date,
                         message=message, web_url=web_url)


class LiveGitlabCommitHistoryClient:
    """Real implementation: GET .../repository/files/:file_path/blame, then
    walk its hunks (each `{commit, lines}`) accumulating line counts until the
    target line falls inside one — GitLab's blame response doesn't carry an
    explicit line number per hunk, only how many lines each commit's hunk
    covers, in file order.
    """

    def __init__(self, host: str, token: str):
        self.host = host.rstrip("/")
        self.token = token
        self._project_id_cache: dict[str, int] = {}

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self.token}

    def _project_id(self, repo: str) -> Optional[int]:
        if repo in self._project_id_cache:
            return self._project_id_cache[repo]
        try:
            resp = requests.get(
                f"{self.host}/api/v4/projects/{quote(repo, safe='')}",
                headers=self._headers(), timeout=10,
            )
            resp.raise_for_status()
            project_id = resp.json()["id"]
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.warning("commit-history project lookup failed for %r: %s", repo, exc)
            return None
        self._project_id_cache[repo] = project_id
        return project_id

    def blame_line(self, repo: str, file: str, line: int) -> Optional[ShippedCommit]:
        project_id = self._project_id(repo)
        if project_id is None:
            return None
        try:
            resp = requests.get(
                f"{self.host}/api/v4/projects/{project_id}/repository/files/{quote(file, safe='')}/blame",
                headers=self._headers(), params={"ref": "master"}, timeout=15,
            )
            resp.raise_for_status()
            hunks = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("blame lookup failed for %r:%r in %r: %s", file, line, repo, exc)
            return None

        cursor = 0
        for hunk in hunks:
            cursor += len(hunk.get("lines") or [])
            if cursor >= line:
                c = hunk.get("commit") or {}
                sha = c.get("id") or ""
                if not sha:
                    return None
                message = (c.get("message") or "").strip().splitlines()
                return ShippedCommit(
                    sha=sha, short_sha=sha[:8],
                    author=c.get("author_name") or "unknown",
                    date=c.get("committed_date") or c.get("authored_date") or "",
                    message=message[0][:200] if message else "",
                    web_url=f"{self.host}/{repo}/-/commit/{sha}",
                )
        return None
