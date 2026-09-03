"""GitLab-backed search for Code Scout.

Two implementations share the same Protocol:
  - FixtureSearchClient: Day-1 demo mode, canned results keyed by finding_rank.
    Mirrors the Fetcher's own `demo_mode` pattern from the plan.
  - LiveGitlabSearchClient: Day-2 real GitLab Search API. Verified live on
    2026-09-03 against gitlab.devops.mhealth.tech - project-scoped
    `scope=blobs` search works with no Advanced Search/Elasticsearch
    dependency, because routing already resolves to one known repo before a
    search ever runs. Confirmed reproducing the hand-verified example
    exactly: bintan/consultation -> ConsultationDao.java:146,
    GET_ABANDON_CONSULTATION.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol
from urllib.parse import quote

import requests

SEARCH_BUDGET_PER_REPO = 5


@dataclass
class GapLocation:
    file: str
    line: int
    snippet: str


class SearchClient(Protocol):
    def find_gap(
        self, finding_rank: int, repo: str, search_terms: list[str]
    ) -> tuple[Optional[GapLocation], int]:
        """Search one repo for one finding. Returns (location_or_None, searches_run)."""
        ...


class FixtureSearchClient:
    """Day-1 / demo mode. Loads pre-proven results from fixtures/code_scout/*.json,
    keyed by finding_rank + repo. Each fixture records how it was actually
    verified (see the `_verified` field) - not fabricated data.
    """

    def __init__(self, fixtures_dir: Path):
        self._fixtures: dict[tuple[int, str], dict] = {}
        for path in sorted(fixtures_dir.glob("*.json")):
            data = json.loads(path.read_text())
            self._fixtures[(data["finding_rank"], data["repo"])] = data

    def find_gap(
        self, finding_rank: int, repo: str, search_terms: list[str]
    ) -> tuple[Optional[GapLocation], int]:
        fixture = self._fixtures.get((finding_rank, repo))
        if fixture is None:
            return None, 1
        if not fixture.get("found", True):
            return None, fixture.get("searches_run", 1)
        return (
            GapLocation(file=fixture["file"], line=fixture["line"], snippet=fixture["snippet"]),
            fixture.get("searches_run", 1),
        )


class LiveGitlabSearchClient:
    """Day-2 real implementation.

    Requires env vars GITLAB_HOST and GITLAB_TOKEN. The token MUST be scoped
    to read_api + read_repository only, per the plan's hard rule (read-only
    everywhere - Code Scout never writes a diff or opens an MR). The test
    token used during verification had broader scope and should have been
    reissued before this class sees real use.
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
        resp = requests.get(
            f"{self.host}/api/v4/projects/{quote(repo_path, safe='')}",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        project_id = resp.json()["id"]
        self._project_id_cache[repo_path] = project_id
        return project_id

    def find_gap(
        self, finding_rank: int, repo: str, search_terms: list[str]
    ) -> tuple[Optional[GapLocation], int]:
        project_id = self._project_id(repo)
        searches_run = 0
        for term in search_terms:
            if searches_run >= SEARCH_BUDGET_PER_REPO:
                break
            searches_run += 1
            resp = requests.get(
                f"{self.host}/api/v4/projects/{project_id}/search",
                headers=self._headers(),
                params={"scope": "blobs", "search": term},
                timeout=15,
            )
            resp.raise_for_status()
            hits = resp.json()
            if not hits:
                continue
            hit = hits[0]
            location = self._resolve_exact_location(
                project_id, hit["path"], hit.get("ref", "master"), term
            )
            if location is not None:
                return location, searches_run
        return None, searches_run

    def _resolve_exact_location(
        self, project_id: int, path: str, ref: str, term: str
    ) -> Optional[GapLocation]:
        """The GitLab search API's inline snippet doesn't reliably pin the exact
        matched line, so fetch the whole raw file and locate the term ourselves -
        this is exactly how ConsultationDao.java:146 was confirmed manually."""
        resp = requests.get(
            f"{self.host}/api/v4/projects/{project_id}/repository/files/{quote(path, safe='')}/raw",
            headers=self._headers(),
            params={"ref": ref},
            timeout=15,
        )
        resp.raise_for_status()
        lines = resp.text.splitlines()
        needle = term.lower()
        for idx, text in enumerate(lines):
            if needle in text.lower():
                line_no = idx + 1
                start = max(0, idx - 6)
                end = min(len(lines), idx + 7)
                snippet = "\n".join(lines[start:end])[:800]
                return GapLocation(file=path, line=line_no, snippet=snippet)
        return None
