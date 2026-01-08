"""Branch management tools for Keboola CLI MCP Server."""

from fastmcp import FastMCP

from ..config import Settings
from ..services.branch_resolver import BranchResolver, BranchResolutionError, ProjectNotInitializedError
from ..services.branch_mapping import (
    create_keboola_branch,
    find_keboola_branch_by_name,
    BranchCreationError,
)
from ..services.git import GitError


def register_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register branch management tools with the MCP server."""

    resolver = BranchResolver(
        working_dir=settings.working_dir,
        mapping_file=settings.get_mapping_file_path(),
        default_branch=settings.git_default_branch,
    )

    @mcp.tool()
    async def link_branch(
        branch_name: str | None = None,
        description: str | None = None
    ) -> dict:
        """
        Links the current git branch to a Keboola development branch.

        If no Keboola branch with the specified name exists, creates one.
        The Keboola branch name defaults to the git branch name if not specified.

        Args:
            branch_name: Optional custom name for the Keboola branch (defaults to git branch name)
            description: Optional description for the new Keboola branch

        Returns:
            Dictionary with git_branch, keboola_branch_id, keboola_branch_name, created, and message

        Raises:
            Error if not in a git repository
            Error if on main/master branch (should use production, not dev branch)
        """
        try:
            git_branch = resolver.get_current_git_branch()
        except GitError as e:
            return {"error": "GIT_ERROR", "message": str(e)}

        # Validate project initialization (only for non-default branches)
        try:
            resolver.validate_project_initialization()
        except ProjectNotInitializedError as e:
            return {
                "error": "PROJECT_NOT_INITIALIZED",
                "message": str(e),
                "fix": "Run 'kbc sync init --allow-target-env' to initialize the project properly"
            }

        # Check if on default branch
        if resolver.is_default_branch(git_branch):
            # Map default branch to production (null)
            resolver.mapping_service.add_mapping(git_branch, None)
            return {
                "git_branch": git_branch,
                "keboola_branch_id": None,
                "keboola_branch_name": "production",
                "created": False,
                "message": f"Default branch '{git_branch}' mapped to production (no KBC_BRANCH_ID override)"
            }

        # Use git branch name as Keboola branch name if not specified
        keboola_branch_name = branch_name or git_branch

        # Check if mapping already exists
        if resolver.mapping_service.has_mapping(git_branch):
            existing_id = resolver.mapping_service.get_mapping(git_branch)
            return {
                "git_branch": git_branch,
                "keboola_branch_id": existing_id,
                "keboola_branch_name": keboola_branch_name,
                "created": False,
                "message": f"Branch already linked to Keboola branch {existing_id}"
            }

        # Try to find existing Keboola branch with this name
        existing_branch = await find_keboola_branch_by_name(
            keboola_branch_name,
            working_dir=settings.working_dir
        )

        if existing_branch:
            # Use existing branch
            branch_id = str(existing_branch.get("id"))
            resolver.mapping_service.add_mapping(git_branch, branch_id)
            return {
                "git_branch": git_branch,
                "keboola_branch_id": branch_id,
                "keboola_branch_name": keboola_branch_name,
                "created": False,
                "message": f"Linked to existing Keboola branch '{keboola_branch_name}' (ID: {branch_id})"
            }

        # Create new Keboola branch
        try:
            branch_data = await create_keboola_branch(
                branch_name=keboola_branch_name,
                description=description,
                working_dir=settings.working_dir
            )
            branch_id = str(branch_data.get("id"))
            resolver.mapping_service.add_mapping(git_branch, branch_id)
            return {
                "git_branch": git_branch,
                "keboola_branch_id": branch_id,
                "keboola_branch_name": keboola_branch_name,
                "created": True,
                "message": f"Successfully created and linked Keboola branch '{keboola_branch_name}' (ID: {branch_id})"
            }
        except BranchCreationError as e:
            return {"error": "BRANCH_CREATION_ERROR", "message": str(e)}

    @mcp.tool()
    async def unlink_branch() -> dict:
        """
        Removes the branch mapping for the current git branch.

        Does NOT delete the Keboola development branch - only removes the local mapping.
        Use the Keboola UI or API to delete the branch if needed.

        Returns:
            Dictionary with git_branch, unlinked_keboola_branch_id, and message
        """
        try:
            git_branch = resolver.get_current_git_branch()
        except GitError as e:
            return {"error": "GIT_ERROR", "message": str(e)}

        if not resolver.mapping_service.has_mapping(git_branch):
            return {
                "git_branch": git_branch,
                "unlinked_keboola_branch_id": None,
                "message": f"No mapping exists for git branch '{git_branch}'"
            }

        keboola_branch_id = resolver.mapping_service.remove_mapping(git_branch)
        return {
            "git_branch": git_branch,
            "unlinked_keboola_branch_id": keboola_branch_id,
            "message": f"Mapping removed. Keboola branch {keboola_branch_id or 'production'} still exists."
        }

    @mcp.tool()
    async def get_mapping() -> dict:
        """
        Gets the Keboola branch mapping for the current git branch.

        This is a safe, read-only operation that always succeeds.

        Returns:
            Dictionary with git_branch, keboola_branch_id, linked, and is_production
        """
        try:
            git_branch = resolver.get_current_git_branch()
        except GitError as e:
            return {"error": "GIT_ERROR", "message": str(e)}

        # Check for explicit mapping
        if resolver.mapping_service.has_mapping(git_branch):
            keboola_branch_id = resolver.mapping_service.get_mapping(git_branch)
            return {
                "git_branch": git_branch,
                "keboola_branch_id": keboola_branch_id,
                "linked": True,
                "is_production": keboola_branch_id is None
            }

        # Check if it's a default branch (implicitly mapped to production)
        if resolver.is_default_branch(git_branch):
            return {
                "git_branch": git_branch,
                "keboola_branch_id": None,
                "linked": True,
                "is_production": True
            }

        # No mapping
        return {
            "git_branch": git_branch,
            "keboola_branch_id": None,
            "linked": False,
            "is_production": False
        }

    @mcp.tool()
    async def list_mappings() -> dict:
        """
        Lists all git-to-Keboola branch mappings.

        Returns:
            Dictionary with mappings dict and current_git_branch
        """
        try:
            git_branch = resolver.get_current_git_branch()
        except GitError:
            git_branch = None

        mappings = resolver.mapping_service.load_mappings()
        return {
            "mappings": mappings,
            "current_git_branch": git_branch
        }
