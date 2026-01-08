"""Pydantic models for the MCP server."""

from pydantic import BaseModel


class BranchMapping(BaseModel):
    """Branch mapping entry."""
    git_branch: str
    keboola_branch_id: str | None
    keboola_branch_name: str | None = None


class BranchInfo(BaseModel):
    """Information about current branch context."""
    git_branch: str
    keboola_branch_id: str | None
    is_production: bool
    linked: bool = True


class CLIResult(BaseModel):
    """Result from CLI command execution."""
    success: bool
    command: str
    git_branch: str
    keboola_branch_id: str | None
    output: str
    exit_code: int
    stderr: str = ""
