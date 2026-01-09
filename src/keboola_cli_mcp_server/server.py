"""FastMCP server setup for Keboola CLI MCP Server."""

from fastmcp import FastMCP, Client
from fastmcp.server.proxy import FastMCPProxy
from fastmcp.client.transports import StreamableHttpTransport

from .config import Settings
from .services.branch_resolver import BranchResolver, BranchResolutionError, ProjectNotInitializedError
from .tools import branch, cli_proxy, docs


def create_server(settings: Settings | None = None) -> FastMCP:
    """
    Create and configure the MCP server.

    Args:
        settings: Optional settings to use. If not provided, settings are loaded from environment.

    Returns:
        Configured FastMCP server instance (either FastMCP or FastMCPProxy depending on proxy_mode)
    """
    if settings is None:
        settings = Settings()

    if settings.proxy_mode:
        return _create_proxy_server(settings)
    else:
        return _create_cli_server(settings)


def _create_cli_server(settings: Settings) -> FastMCP:
    """
    Create a CLI-only server (no proxy to remote Keboola MCP server).

    This mode provides:
    - Branch management tools (link_branch, unlink_branch, etc.)
    - CLI proxy tool (kbc) for running kbc commands
    - Documentation search tool
    """
    mcp = FastMCP(
        name="keboola-cli",
        instructions="""
Keboola CLI MCP Server - Deterministic branch-aware CLI proxy.

This server provides tools to interact with the Keboola CLI (kbc) with automatic
git-to-Keboola branch mapping. Before running CLI commands, you must link your
git branch to a Keboola development branch.

Workflow:
1. Use 'get_mapping' to check if current git branch is linked
2. If not linked, use 'link_branch' to create/link to a Keboola branch
3. Then use 'kbc' tool to run CLI commands (sync push, sync pull, etc.)

The server ensures you always work in the correct Keboola branch context.
"""
    )

    # Register tools
    branch.register_tools(mcp, settings)
    cli_proxy.register_tools(mcp, settings)
    docs.register_tools(mcp, settings)

    return mcp


def _create_proxy_server(settings: Settings) -> FastMCPProxy:
    """
    Create a proxy server that forwards requests to remote Keboola MCP server.

    This mode provides:
    - All tools from the remote Keboola MCP server (SQL workspace, table operations, etc.)
    - Automatic X-Branch-Id header injection based on current git branch
    - Local CLI tools (link_branch, kbc, etc.)

    The X-Branch-Id header is resolved dynamically per-request, so switching git
    branches immediately affects which Keboola branch is targeted.
    """
    resolver = BranchResolver(
        working_dir=settings.working_dir,
        mapping_file=settings.get_mapping_file_path(),
        default_branch=settings.git_default_branch,
    )

    def branch_aware_client_factory() -> Client:
        """
        Create a client with dynamic branch ID header injection.

        Called per-request, so branch is resolved fresh each time.
        This ensures switching git branches immediately takes effect.
        """
        headers = {
            "X-StorageAPI-Token": settings.storage_token,
        }

        # Resolve current git branch to Keboola branch ID
        try:
            resolver.validate_project_initialization()
            git_branch = resolver.get_current_git_branch()
            branch_id = resolver.get_keboola_branch_id(git_branch)

            if branch_id:
                headers["X-Branch-Id"] = branch_id

        except (BranchResolutionError, ProjectNotInitializedError):
            # If branch resolution fails, proceed without X-Branch-Id
            # The remote server will use the default branch
            # Errors will surface when CLI tools are used
            pass

        transport = StreamableHttpTransport(
            url=settings.get_mcp_server_url(),
            headers=headers,
        )

        return Client(transport)

    mcp = FastMCPProxy(
        name="keboola-unified",
        client_factory=branch_aware_client_factory,
        instructions="""
Keboola Unified MCP Server - Branch-aware proxy to Keboola platform.

This server combines:
- Remote Keboola MCP server tools (SQL workspace, table operations, jobs, etc.)
- Local CLI tools (kbc commands, branch management)

All operations automatically target the correct Keboola branch based on your
current git branch. The branch mapping is resolved per-request, so switching
git branches immediately affects which Keboola branch is targeted.

Workflow:
1. Use 'get_mapping' to check if current git branch is linked
2. If not linked, use 'link_branch' to create/link to a Keboola branch
3. Then use any tool - they will all target the correct branch

Branch Management:
- link_branch: Link current git branch to a Keboola development branch
- unlink_branch: Remove branch mapping
- get_mapping: Check current branch mapping status
- list_mappings: List all branch mappings

CLI Tools:
- kbc: Run Keboola CLI commands (sync push, sync pull, sync diff, etc.)

Remote Tools (from Keboola MCP server):
- SQL workspace queries
- Table operations (preview, download, upload)
- Job management
- And more...
"""
    )

    # Register local CLI tools (these take precedence over remote tools with same name)
    branch.register_tools(mcp, settings)
    cli_proxy.register_tools(mcp, settings)
    docs.register_tools(mcp, settings)

    return mcp
