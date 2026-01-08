"""Git operations service."""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""
    pass


class GitService:
    """Service for git operations."""

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir

    def get_current_branch(self) -> str:
        """Get the current git branch name."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                check=True
            )
            branch = result.stdout.strip()
            if not branch:
                raise GitError("Not on a branch (possibly detached HEAD)")
            return branch
        except subprocess.CalledProcessError as e:
            raise GitError(f"Failed to get current branch: {e.stderr}") from e

    def is_git_repository(self) -> bool:
        """Check if the working directory is a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.working_dir,
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def create_branch(self, branch_name: str, checkout: bool = True) -> None:
        """Create a new git branch."""
        try:
            if checkout:
                subprocess.run(
                    ["git", "checkout", "-b", branch_name],
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
            else:
                subprocess.run(
                    ["git", "branch", branch_name],
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
        except subprocess.CalledProcessError as e:
            raise GitError(f"Failed to create branch: {e.stderr}") from e
