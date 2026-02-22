"""Documentation search tool for Keboola CLI MCP Server."""

from fastmcp import FastMCP

from ..config import Settings
from ..services.sapi_client import AIServiceClient


def register_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register documentation tools with the MCP server."""

    # Create AI service client from storage API URL
    ai_client = AIServiceClient.from_storage_url(
        storage_api_url=settings.storage_api_url,
        token=settings.storage_token,
    )

    @mcp.tool()
    async def search_cli_docs(query: str) -> dict:
        """
        Search Keboola CLI documentation for commands, flags, environment variables, and workflows.

        Use this to find information about kbc commands like sync, push, pull, remote, local,
        branch management, environment variables (KBC_BRANCH_ID, KBC_STORAGE_API_TOKEN), and DevOps workflows.

        Args:
            query: Search query (e.g., 'how to push changes', 'branch environment variables', 'sync init flags')

        Returns:
            Dictionary with results list and the query used
        """
        # Prefix query to scope results to CLI documentation
        cli_query = f"Keboola CLI kbc command: {query}"

        try:
            response = await ai_client.docs_question(cli_query)
            return {
                "results": [
                    {
                        "text": response.text,
                        "source_urls": response.source_urls
                    }
                ],
                "query": cli_query
            }
        except Exception as e:
            return {
                "error": "DOCS_QUERY_ERROR",
                "message": str(e),
                "query": cli_query
            }
