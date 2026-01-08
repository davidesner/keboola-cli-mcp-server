"""Configuration management for Keboola CLI MCP Server."""

import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Server settings loaded from environment variables."""

    storage_token: str = Field(default_factory=lambda: os.environ.get("KBC_STORAGE_TOKEN", ""))
    storage_api_url: str = Field(default_factory=lambda: os.environ.get("KBC_STORAGE_API_URL", "https://connection.keboola.com"))
    git_default_branch: str = Field(default_factory=lambda: os.environ.get("GIT_DEFAULT_BRANCH", "main"))
    working_dir: Path = Field(default_factory=lambda: Path(os.environ.get("KBC_WORKING_DIR", os.getcwd())))
    mapping_file: Path = Field(default_factory=lambda: Path(os.environ.get("KBC_MAPPING_FILE", "branch-mapping.json")))

    def get_mapping_file_path(self) -> Path:
        """Get the absolute path to the mapping file."""
        if self.mapping_file.is_absolute():
            return self.mapping_file
        return self.working_dir / self.mapping_file

    def validate_required(self) -> None:
        """Validate that required settings are present."""
        if not self.storage_token:
            raise ValueError("KBC_STORAGE_TOKEN environment variable is required")
        if not self.storage_api_url:
            raise ValueError("KBC_STORAGE_API_URL environment variable is required")
