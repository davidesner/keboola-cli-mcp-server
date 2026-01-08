"""FastMCP server setup for Keboola CLI MCP Server."""

from fastmcp import FastMCP

from .config import Settings
from .tools import branch, cli_proxy, docs


def create_server(settings: Settings | None = None) -> FastMCP:
    """
    Create and configure the MCP server.

    Args:
        settings: Optional settings to use. If not provided, settings are loaded from environment.

    Returns:
        Configured FastMCP server instance
    """
    if settings is None:
        settings = Settings()

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
