"""Core branch resolution logic."""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from .git import GitService, GitError
from .branch_mapping import BranchMappingService


class BranchResolutionError(Exception):
    """Raised when branch mapping is not found."""
    pass


class ProjectNotInitializedError(Exception):
    """Raised when Keboola project is not properly initialized."""
    pass


class BranchResolver:
    """
    Core branch resolution service.

    Provides deterministic mapping from git branches to Keboola branches.
    """

    def __init__(
        self,
        working_dir: Path,
        mapping_file: Path,
        default_branch: str = "main"
    ):
        self.working_dir = working_dir
        self.mapping_file = mapping_file
        self.default_branch = default_branch
        self._git_service = GitService(working_dir)
        self._mapping_service = BranchMappingService(mapping_file)

    @property
    def git_service(self) -> GitService:
        return self._git_service

    @property
    def mapping_service(self) -> BranchMappingService:
        return self._mapping_service

    def validate_project_initialization(self) -> None:
        """
        Validate that the Keboola project is properly initialized.

        Checks:
        1. .keboola/manifest.json exists
        2. allowTargetEnv is set to true (required for KBC_BRANCH_ID override)

        Raises:
            ProjectNotInitializedError if validation fails
        """
        manifest_file = self.working_dir / ".keboola" / "manifest.json"

        if not manifest_file.exists():
            raise ProjectNotInitializedError(
                "PROJECT_NOT_INITIALIZED: Keboola project is not initialized. "
                "Run 'kbc sync init --allow-target-env' first."
            )

        try:
            manifest = json.loads(manifest_file.read_text())
        except json.JSONDecodeError as e:
            raise ProjectNotInitializedError(
                f"PROJECT_INVALID: Failed to parse manifest.json: {e}"
            )

        if not manifest.get("allowTargetEnv", False):
            raise ProjectNotInitializedError(
                "PROJECT_MISCONFIGURED: The project was not initialized with --allow-target-env flag. "
                "The KBC_BRANCH_ID environment variable override will NOT work. "
                "Re-initialize the project with: kbc sync init --allow-target-env"
            )

    def get_current_git_branch(self) -> str:
        """Get the current git branch name."""
        return self._git_service.get_current_branch()

    def is_default_branch(self, git_branch: str) -> bool:
        """Check if the git branch is the default branch (main/master)."""
        return git_branch in (self.default_branch, "main", "master")

    def get_keboola_branch_id(self, git_branch: str) -> str | None:
        """
        Get the Keboola branch ID for a git branch.

        Returns:
            Branch ID string, or None for production (main/master)

        Raises:
            BranchResolutionError if no mapping exists (unless on default branch)
        """
        # Check if it's the default branch - maps to production (None)
        if self.is_default_branch(git_branch):
            return None

        # Check for explicit mapping
        if self._mapping_service.has_mapping(git_branch):
            return self._mapping_service.get_mapping(git_branch)

        # No mapping found - raise error
        available = list(self._mapping_service.load_mappings().keys())
        raise BranchResolutionError(
            f'NO_MAPPING: Git branch "{git_branch}" is not linked to any Keboola branch. '
            f'Use the "link_branch" tool first. Available mappings: {available}'
        )

    def resolve_current_branch(self) -> tuple[str, str | None]:
        """
        Resolve the current git branch to its Keboola branch ID.

        Returns:
            Tuple of (git_branch, keboola_branch_id)
        """
        git_branch = self.get_current_git_branch()
        keboola_branch_id = self.get_keboola_branch_id(git_branch)
        return git_branch, keboola_branch_id

    @asynccontextmanager
    async def branch_context(self) -> AsyncIterator[tuple[dict, dict]]:
        """
        Context manager that provides environment with correct KBC_BRANCH_ID.

        Usage:
            async with resolver.branch_context() as (env, branch_info):
                result = subprocess.run(["kbc", "sync", "push"], env=env)

        Yields:
            Tuple of (env dict, branch_info dict)

        Raises:
            ProjectNotInitializedError if project is not properly initialized
            BranchResolutionError if no mapping exists for the current branch
        """
        # Validate project initialization first
        self.validate_project_initialization()

        git_branch = self.get_current_git_branch()
        keboola_branch_id = self.get_keboola_branch_id(git_branch)

        env = os.environ.copy()

        if keboola_branch_id is not None:
            env["KBC_BRANCH_ID"] = keboola_branch_id
        elif "KBC_BRANCH_ID" in env:
            # Production branch - ensure no branch ID is set
            del env["KBC_BRANCH_ID"]

        branch_info = {
            "git_branch": git_branch,
            "keboola_branch_id": keboola_branch_id,
            "is_production": keboola_branch_id is None
        }

        yield env, branch_info
