"""Tests for branch management tools."""

import json
import subprocess
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from keboola_cli_mcp_server.config import Settings
from keboola_cli_mcp_server.services.branch_resolver import BranchResolver
from keboola_cli_mcp_server.services.branch_mapping import BranchMappingService


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # Create initial commit
    (tmp_path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def settings(temp_git_repo):
    """Create test settings."""
    return Settings(
        storage_token="test-token",
        storage_api_url="https://connection.keboola.com",
        working_dir=temp_git_repo,
        mapping_file=temp_git_repo / "branch-mapping.json",
    )


class TestBranchToolsIntegration:
    def test_settings_mapping_file_path(self, settings, temp_git_repo):
        """Test that settings correctly resolves mapping file path."""
        assert settings.get_mapping_file_path() == temp_git_repo / "branch-mapping.json"

    def test_resolver_creation(self, settings):
        """Test that resolver can be created from settings."""
        resolver = BranchResolver(
            working_dir=settings.working_dir,
            mapping_file=settings.get_mapping_file_path(),
            default_branch=settings.git_default_branch,
        )
        assert resolver.get_current_git_branch() == "main"

    def test_mapping_persistence(self, settings):
        """Test that mappings persist correctly."""
        mapping_service = BranchMappingService(settings.get_mapping_file_path())

        # Add mapping
        mapping_service.add_mapping("feature/test", "12345")

        # Create new service instance and verify persistence
        new_service = BranchMappingService(settings.get_mapping_file_path())
        assert new_service.get_mapping("feature/test") == "12345"

    def test_complete_workflow(self, settings, temp_git_repo):
        """Test a complete branch linking workflow."""
        resolver = BranchResolver(
            working_dir=settings.working_dir,
            mapping_file=settings.get_mapping_file_path(),
            default_branch=settings.git_default_branch,
        )

        # Create feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/workflow-test"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Verify no mapping exists initially
        assert not resolver.mapping_service.has_mapping("feature/workflow-test")

        # Add mapping
        resolver.mapping_service.add_mapping("feature/workflow-test", "99999")

        # Verify mapping exists
        assert resolver.mapping_service.has_mapping("feature/workflow-test")
        assert resolver.get_keboola_branch_id("feature/workflow-test") == "99999"

        # Remove mapping
        removed = resolver.mapping_service.remove_mapping("feature/workflow-test")
        assert removed == "99999"
        assert not resolver.mapping_service.has_mapping("feature/workflow-test")
