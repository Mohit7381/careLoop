"""GitLab-backed EXPLORE search for Code Scout's alternate Suggestion flow
(Rev 3, PR #3, kept additive alongside search_client.py's find_gap() -
see contracts.py's module docstring, decision #11).

find_gap() (search_client.py) stops at the first hit and answers "where is
the one mechanism causing this finding". explore() here answers a different
question - "what already exists in this feature area" - by collecting
several distinct hits into a small inventory instead of stopping at the
first, so suggestion_assessor.py's propose_suggestions() has more than one
data point to reason from. check_within_file() then verifies whether a
specific proposed capability already exists in a specific file - narrower
than explore()'s whole-repo search, because a whole-repo search for a
signature like "garuda" false-positives when Garuda infrastructure exists
elsewhere in the service for unrelated purposes.

Shares search_client.py's GapLocation shape, is_source_path() path filter,
and CodeScoutExternalError resilience pattern rather than duplicating them.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional, Protocol
from urllib.parse import quote

import requests

from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.search_client import GapLocation, is_source_path

logger = logging.getLogger(__name__)

EXPLORATION_SEARCH_BUDGET = 8  # searches to build the feature inventory, per finding


class ExploreSearchClient(Protocol):
    def explore(
        self, finding_rank: int, repo: str, search_terms: list[str], budget: int
    ) -> tuple[list[GapLocation], int]:
        """Search a repo across search_terms, collecting distinct hits into a
        small feature inventory (not stopping at the first) - up to `budget`
        searches. Returns (inventory, searches_run)."""
        ...

    def check_within_file(
        self, finding_rank: int, repo: str, file: str, term: str
    ) -> Optional[int]:
        """Does `term` appear inside this specific file? Returns the line
        number if so, else None."""
        ...


class FixtureExploreSearchClient:
    """Day-1 / demo mode. Loads pre-proven results from
    fixtures/code_scout_suggestions/*.json, keyed by finding_rank + repo.
    Each fixture records how it was actually verified (see the `_verified`
    field) - not fabricated data."""

    def __init__(self, fixtures_dir: Path):
        self._fixtures: dict[tuple[int, str], dict] = {}
        self._verification_checks: dict[int, dict] = {}
        for path in sorted(fixtures_dir.glob("*.json")):
            data = json.loads(path.read_text())
            self._fixtures[(data["finding_rank"], data["repo"])] = data
            checks = data.get("verification_checks")
            if checks:
                self._verification_checks[data["finding_rank"]] = checks

    def explore(
        self, finding_rank: int, repo: str, search_terms: list[str], budget: int
    ) -> tuple[list[GapLocation], int]:
        fixture = self._fixtures.get((finding_rank, repo))
        if fixture is None or not fixture.get("inventory"):
            return [], min(1, budget)
        inventory = [
            GapLocation(file=item["file"], line=item["line"], snippet=item.get("snippet", ""))
            for item in fixture["inventory"]
        ]
        return inventory, fixture.get("searches_run", 1)

    def check_within_file(
        self, finding_rank: int, repo: str, file: str, term: str
    ) -> Optional[int]:
        checks = self._verification_checks.get(finding_rank, {})
        return checks.get(term)


class LiveGitlabExploreSearchClient:
    """Day-2 real implementation.

    Requires env vars GITLAB_HOST and GITLAB_TOKEN. The token MUST be scoped
    to read_api + read_repository only (Code Scout never writes a diff or
    opens an MR).
    """

    def __init__(self, host: Optional[str] = None, token: Optional[str] = None):
        self.host = (host or os.environ["GITLAB_HOST"]).rstrip("/")
        self.token = token or os.environ["GITLAB_TOKEN"]
        self._project_id_cache: dict[str, int] = {}

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self.token}

    def _project_id(self, repo_path: str) -> int:
        if repo_path in self._project_id_cache:
            return self._project_id_cache[repo_path]
        try:
            resp = requests.get(
                f"{self.host}/api/v4/projects/{quote(repo_path, safe='')}",
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            project_id = resp.json()["id"]
        except requests.RequestException as exc:
            raise CodeScoutExternalError(f"GitLab project lookup failed for {repo_path!r}: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise CodeScoutExternalError(
                f"GitLab project lookup returned an unexpected response for {repo_path!r}: {exc}"
            ) from exc
        self._project_id_cache[repo_path] = project_id
        return project_id

    def explore(
        self, finding_rank: int, repo: str, search_terms: list[str], budget: int
    ) -> tuple[list[GapLocation], int]:
        project_id = self._project_id(repo)
        inventory: list[GapLocation] = []
        seen_files: set[str] = set()
        searches_run = 0

        for term in search_terms:
            if searches_run >= budget:
                break
            searches_run += 1
            try:
                resp = requests.get(
                    f"{self.host}/api/v4/projects/{project_id}/search",
                    headers=self._headers(),
                    params={"scope": "blobs", "search": term},
                    timeout=15,
                )
                resp.raise_for_status()
                hits = resp.json()
            except requests.RequestException as exc:
                logger.warning("GitLab search failed for term %r in %r: %s", term, repo, exc)
                continue
            except ValueError as exc:
                logger.warning("GitLab search returned invalid JSON for term %r in %r: %s", term, repo, exc)
                continue

            hit = next(
                (h for h in hits if isinstance(h, dict) and "path" in h and is_source_path(h["path"])),
                None,
            )
            if hit is None or hit["path"] in seen_files:
                continue
            try:
                location = self._resolve_exact_location(
                    project_id, hit["path"], hit.get("ref", "master"), term
                )
            except CodeScoutExternalError as exc:
                logger.warning("Could not resolve exact location for %r in %r: %s", hit["path"], repo, exc)
                continue
            if location is not None:
                inventory.append(location)
                seen_files.add(location.file)

        return inventory, searches_run

    def check_within_file(
        self, finding_rank: int, repo: str, file: str, term: str
    ) -> Optional[int]:
        project_id = self._project_id(repo)
        lines = self._fetch_raw_lines(project_id, file, "master")
        needle = term.lower()
        for idx, text in enumerate(lines):
            if needle in text.lower():
                return idx + 1
        return None

    def _fetch_raw_lines(self, project_id: int, path: str, ref: str) -> list[str]:
        try:
            resp = requests.get(
                f"{self.host}/api/v4/projects/{project_id}/repository/files/{quote(path, safe='')}/raw",
                headers=self._headers(),
                params={"ref": ref},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CodeScoutExternalError(f"GitLab raw file fetch failed for {path!r}: {exc}") from exc
        return resp.text.splitlines()

    def _resolve_exact_location(
        self, project_id: int, path: str, ref: str, term: str
    ) -> Optional[GapLocation]:
        lines = self._fetch_raw_lines(project_id, path, ref)
        needle = term.lower()
        for idx, text in enumerate(lines):
            if needle in text.lower():
                line_no = idx + 1
                start = max(0, idx - 6)
                end = min(len(lines), idx + 7)
                snippet = "\n".join(lines[start:end])[:800]
                return GapLocation(file=path, line=line_no, snippet=snippet)
        return None
