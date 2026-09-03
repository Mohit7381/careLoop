"""
Read-only GitLab client (PAT). OWNER: Harshit.

Used by Code Scout to blob-search the owning repo for a finding's stage,
fetch the top matching files, and cite file:line in the emitted CodeGap.
Never writes diffs, never opens MRs — search + read only.

NOT YET IMPLEMENTED. This is the seam app/pipeline/nodes/code_scout.py
calls into once the stub search functions are replaced.
"""
from typing import Any

from app.config import get_settings


class GitLabClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def blob_search(self, repo: str, terms: list[str]) -> list[dict[str, Any]]:
        raise NotImplementedError("Harshit: wire this to GitLab's search API (scope=blobs) for `repo`")

    def fetch_file(self, repo: str, file_path: str, ref: str = "master") -> str:
        raise NotImplementedError("Harshit: fetch raw file content via the GitLab Repository Files API")
