"""Entry point for Keboola CLI MCP Server."""

from .server import create_server


def main():
    """Run the MCP server."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
