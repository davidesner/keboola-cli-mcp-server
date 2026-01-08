"""Tests for BranchResolver service."""

import json
import subprocess
import pytest
from pathlib import Path

from keboola_cli_mcp_server.services.branch_resolver import (
    BranchResolver,
    BranchResolutionError,
    ProjectNotInitializedError,
)
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
    # Create initial commit so we can create branches
    (tmp_path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # Rename default branch to 'main' if needed
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def mock_mapping_file(tmp_path):
    """Create a temporary mapping file."""
    mapping_file = tmp_path / "branch-mapping.json"
    mapping_file.write_text('{"main": null, "feature/test": "12345"}')
    return mapping_file


class TestBranchMappingService:
    def test_load_empty_mappings(self, tmp_path):
        """Test loading mappings when file doesn't exist."""
        mapping_file = tmp_path / "branch-mapping.json"
        service = BranchMappingService(mapping_file)
        assert service.load_mappings() == {}

    def test_load_existing_mappings(self, mock_mapping_file):
        """Test loading existing mappings."""
        service = BranchMappingService(mock_mapping_file)
        mappings = service.load_mappings()
        assert mappings == {"main": None, "feature/test": "12345"}

    def test_save_mappings(self, tmp_path):
        """Test saving mappings atomically."""
        mapping_file = tmp_path / "branch-mapping.json"
        service = BranchMappingService(mapping_file)

        service.save_mappings({"main": None, "feature/new": "67890"})

        assert mapping_file.exists()
        content = json.loads(mapping_file.read_text())
        assert content == {"main": None, "feature/new": "67890"}

    def test_add_mapping(self, tmp_path):
        """Test adding a new mapping."""
        mapping_file = tmp_path / "branch-mapping.json"
        service = BranchMappingService(mapping_file)

        service.add_mapping("feature/new", "12345")

        mappings = service.load_mappings()
        assert mappings["feature/new"] == "12345"

    def test_remove_mapping(self, mock_mapping_file):
        """Test removing a mapping."""
        service = BranchMappingService(mock_mapping_file)

        removed = service.remove_mapping("feature/test")

        assert removed == "12345"
        assert not service.has_mapping("feature/test")

    def test_has_mapping(self, mock_mapping_file):
        """Test checking if mapping exists."""
        service = BranchMappingService(mock_mapping_file)

        assert service.has_mapping("main")
        assert service.has_mapping("feature/test")
        assert not service.has_mapping("feature/nonexistent")


class TestBranchResolver:
    def test_get_current_git_branch(self, temp_git_repo):
        """Test getting current git branch."""
        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
        )
        assert resolver.get_current_git_branch() == "main"

    def test_get_current_git_branch_feature(self, temp_git_repo):
        """Test getting current git branch on feature branch."""
        subprocess.run(
            ["git", "checkout", "-b", "feature/test"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
        )
        assert resolver.get_current_git_branch() == "feature/test"

    def test_is_default_branch(self, temp_git_repo):
        """Test default branch detection."""
        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
            default_branch="main",
        )

        assert resolver.is_default_branch("main")
        assert resolver.is_default_branch("master")
        assert not resolver.is_default_branch("feature/test")

    def test_get_keboola_branch_id_for_default(self, temp_git_repo):
        """Test that default branch returns None (production)."""
        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
            default_branch="main",
        )

        # Default branch should map to production (None)
        assert resolver.get_keboola_branch_id("main") is None

    def test_get_keboola_branch_id_with_mapping(self, temp_git_repo, mock_mapping_file):
        """Test getting branch ID when mapping exists."""
        # Copy mapping file to temp repo
        (temp_git_repo / "branch-mapping.json").write_text(
            mock_mapping_file.read_text()
        )

        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
        )

        assert resolver.get_keboola_branch_id("feature/test") == "12345"

    def test_get_keboola_branch_id_no_mapping(self, temp_git_repo):
        """Test that missing mapping raises error."""
        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
        )

        with pytest.raises(BranchResolutionError) as exc_info:
            resolver.get_keboola_branch_id("feature/unknown")

        assert "NO_MAPPING" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_branch_context_with_mapping(self, temp_git_repo):
        """Test branch context manager sets correct environment."""
        # Create mapping file
        mapping_file = temp_git_repo / "branch-mapping.json"
        mapping_file.write_text('{"feature/test": "12345"}')

        # Create mock manifest file with allowTargetEnv
        keboola_dir = temp_git_repo / ".keboola"
        keboola_dir.mkdir(exist_ok=True)
        manifest_file = keboola_dir / "manifest.json"
        manifest_file.write_text('{"allowTargetEnv": true}')

        # Switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/test"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=mapping_file,
        )

        async with resolver.branch_context() as (env, branch_info):
            assert env["KBC_BRANCH_ID"] == "12345"
            assert branch_info["git_branch"] == "feature/test"
            assert branch_info["keboola_branch_id"] == "12345"
            assert not branch_info["is_production"]

    @pytest.mark.asyncio
    async def test_branch_context_production(self, temp_git_repo):
        """Test branch context for production branch."""
        # Create mock manifest file with allowTargetEnv
        keboola_dir = temp_git_repo / ".keboola"
        keboola_dir.mkdir(exist_ok=True)
        manifest_file = keboola_dir / "manifest.json"
        manifest_file.write_text('{"allowTargetEnv": true}')

        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
            default_branch="main",
        )

        async with resolver.branch_context() as (env, branch_info):
            assert "KBC_BRANCH_ID" not in env
            assert branch_info["git_branch"] == "main"
            assert branch_info["keboola_branch_id"] is None
            assert branch_info["is_production"]

    def test_validate_project_not_initialized(self, temp_git_repo):
        """Test validation fails when project is not initialized."""
        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
        )

        with pytest.raises(ProjectNotInitializedError) as exc_info:
            resolver.validate_project_initialization()

        assert "PROJECT_NOT_INITIALIZED" in str(exc_info.value)

    def test_validate_project_missing_allow_target_env(self, temp_git_repo):
        """Test validation fails when allowTargetEnv is false."""
        keboola_dir = temp_git_repo / ".keboola"
        keboola_dir.mkdir(exist_ok=True)
        manifest_file = keboola_dir / "manifest.json"
        manifest_file.write_text('{"allowTargetEnv": false}')

        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
        )

        with pytest.raises(ProjectNotInitializedError) as exc_info:
            resolver.validate_project_initialization()

        assert "PROJECT_MISCONFIGURED" in str(exc_info.value)
        assert "--allow-target-env" in str(exc_info.value)

    def test_validate_project_properly_initialized(self, temp_git_repo):
        """Test validation passes when project is properly initialized."""
        keboola_dir = temp_git_repo / ".keboola"
        keboola_dir.mkdir(exist_ok=True)
        manifest_file = keboola_dir / "manifest.json"
        manifest_file.write_text('{"allowTargetEnv": true}')

        resolver = BranchResolver(
            working_dir=temp_git_repo,
            mapping_file=temp_git_repo / "branch-mapping.json",
        )

        # Should not raise
        resolver.validate_project_initialization()
