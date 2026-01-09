"""Configuration management for Keboola CLI MCP Server."""

import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Server settings loaded from environment variables."""

    storage_token: str = Field(default_factory=lambda: os.environ.get("KBC_STORAGE_TOKEN", ""))
    storage_api_url: str = Field(default_factory=lambda: os.environ.get("KBC_STORAGE_API_URL", "https://connection.keboola.com"))
    git_default_branch: str = Field(default_factory=lambda: os.environ.get("GIT_DEFAULT_BRANCH", "main"))
    working_dir: Path = Field(default_factory=lambda: Path(os.environ.get("KBC_WORKING_DIR", os.getcwd())))
    mapping_file: Path = Field(default_factory=lambda: Path(os.environ.get("KBC_MAPPING_FILE", "branch-mapping.json")))

    # Proxy mode: when enabled, proxies to remote Keboola MCP server with branch injection
    proxy_mode: bool = Field(default_factory=lambda: os.environ.get("KBC_MCP_PROXY_MODE", "").lower() in ("true", "1", "yes"))

    def get_mapping_file_path(self) -> Path:
        """Get the absolute path to the mapping file."""
        if self.mapping_file.is_absolute():
            return self.mapping_file
        return self.working_dir / self.mapping_file

    def get_mcp_server_url(self) -> str:
        """
        Derive the Keboola MCP Agent server URL from the Storage API URL.

        Transforms:
            https://connection.us-east4.gcp.keboola.com
            → https://mcp-agent.us-east4.gcp.keboola.com/mcp

            https://connection.keboola.com
            → https://mcp-agent.keboola.com/mcp

        The mcp-agent endpoint accepts X-StorageAPI-Token header for authentication.
        """
        parsed = urlparse(self.storage_api_url)
        host = parsed.netloc

        # Replace 'connection.' prefix with 'mcp-agent.'
        if host.startswith("connection."):
            mcp_host = "mcp-agent." + host[len("connection."):]
        else:
            # Fallback: prepend mcp-agent. to the host
            mcp_host = "mcp-agent." + host

        return f"{parsed.scheme}://{mcp_host}/mcp"

    def validate_required(self) -> None:
        """Validate that required settings are present."""
        if not self.storage_token:
            raise ValueError("KBC_STORAGE_TOKEN environment variable is required")
        if not self.storage_api_url:
            raise ValueError("KBC_STORAGE_API_URL environment variable is required")
