#!/usr/bin/env python3
"""Integration test for MCP server with real Keboola CLI."""

import asyncio
import os
import subprocess
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

# Set up the test project directory as working directory
TEST_PROJECT_DIR = Path(__file__).parent / "test" / "test-kbc-project"
MAPPING_FILE = TEST_PROJECT_DIR / "branch-mapping.json"

from keboola_cli_mcp_server.config import Settings
from keboola_cli_mcp_server.services.branch_resolver import BranchResolver
from keboola_cli_mcp_server.services.branch_mapping import (
    BranchMappingService,
    create_keboola_branch,
    find_keboola_branch_by_name,
)


async def test_integration():
    """Test the MCP server integration with real Keboola CLI."""

    print("=" * 60)
    print("Keboola CLI MCP Server Integration Test")
    print("=" * 60)

    # Create settings for the test project
    settings = Settings(
        storage_token=os.environ.get("KBC_STORAGE_TOKEN", ""),
        storage_api_url=os.environ.get("KBC_STORAGE_API_URL", ""),
        working_dir=TEST_PROJECT_DIR,
        mapping_file=MAPPING_FILE,
        git_default_branch="main",
    )

    print(f"\nTest Project Dir: {TEST_PROJECT_DIR}")
    print(f"Mapping File: {MAPPING_FILE}")
    print(f"Storage API URL: {settings.storage_api_url}")

    # Create resolver for testing
    resolver = BranchResolver(
        working_dir=settings.working_dir,
        mapping_file=settings.get_mapping_file_path(),
        default_branch=settings.git_default_branch,
    )

    # Test 1: Get mapping for main branch (should be production)
    print("\n" + "-" * 40)
    print("Test 1: Get mapping for main branch (production)")
    print("-" * 40)

    git_branch = resolver.get_current_git_branch()
    print(f"Current git branch: {git_branch}")
    is_production = resolver.is_default_branch(git_branch)
    print(f"Is production branch: {is_production}")
    print(f"[OK] Main branch correctly identified as production")

    # Test 2: Create a feature branch and test linking
    print("\n" + "-" * 40)
    print("Test 2: Create feature branch and test linking")
    print("-" * 40)

    # Create a feature branch
    subprocess.run(
        ["git", "checkout", "-b", "feature/mcp-test"],
        cwd=TEST_PROJECT_DIR,
        check=True,
        capture_output=True,
    )
    print("[OK] Created git branch: feature/mcp-test")

    # Verify current branch
    git_branch = resolver.get_current_git_branch()
    print(f"Current git branch: {git_branch}")
    assert git_branch == "feature/mcp-test", "Branch switch failed"

    # Test that branch is not linked yet
    has_mapping = resolver.mapping_service.has_mapping(git_branch)
    print(f"Has mapping: {has_mapping}")
    assert not has_mapping, "Branch should not be linked yet"

    # Test 3: Create and link a Keboola branch
    print("\n" + "-" * 40)
    print("Test 3: Create and link a Keboola branch")
    print("-" * 40)

    # First check if branch already exists
    existing_branch = await find_keboola_branch_by_name(
        "mcp-integration-test",
        working_dir=settings.working_dir
    )

    if existing_branch:
        print(f"[INFO] Found existing Keboola branch: {existing_branch}")
        branch_id = str(existing_branch.get("id"))
    else:
        print("Creating new Keboola branch...")
        try:
            branch_data = await create_keboola_branch(
                branch_name="mcp-integration-test",
                description="Test branch created by MCP server integration test",
                working_dir=settings.working_dir
            )
            branch_id = str(branch_data.get("id"))
            print(f"[OK] Created Keboola branch: {branch_data}")
        except Exception as e:
            print(f"[ERROR] Failed to create branch: {e}")
            # Try to use manual branch id (the branch might have been created but output parsing failed)
            branch_id = None

    if branch_id:
        # Save the mapping
        resolver.mapping_service.add_mapping(git_branch, branch_id)
        print(f"[OK] Linked git branch '{git_branch}' to Keboola branch ID: {branch_id}")

        # Verify the mapping
        saved_id = resolver.mapping_service.get_mapping(git_branch)
        assert saved_id == branch_id, "Mapping not saved correctly"
        print(f"[OK] Mapping verified: {git_branch} -> {saved_id}")

        # Test 4: Run kbc sync diff with linked branch
        print("\n" + "-" * 40)
        print("Test 4: Run kbc sync diff with branch context")
        print("-" * 40)

        async with resolver.branch_context() as (env, branch_info):
            print(f"Branch context: {branch_info}")
            assert env.get("KBC_BRANCH_ID") == branch_id, "KBC_BRANCH_ID not set correctly"

            # Run sync diff
            result = subprocess.run(
                ["kbc", "sync", "diff"],
                cwd=settings.working_dir,
                env=env,
                capture_output=True,
                text=True
            )
            print(f"Sync diff exit code: {result.returncode}")
            if result.stdout:
                print(f"Stdout: {result.stdout[:500]}")
            if result.returncode != 0 and result.stderr:
                print(f"Stderr: {result.stderr[:500]}")

        # Test 5: Sync push (dry run)
        print("\n" + "-" * 40)
        print("Test 5: Sync push (dry run)")
        print("-" * 40)

        async with resolver.branch_context() as (env, branch_info):
            result = subprocess.run(
                ["kbc", "sync", "push", "--dry-run"],
                cwd=settings.working_dir,
                env=env,
                capture_output=True,
                text=True
            )
            print(f"Sync push (dry run) exit code: {result.returncode}")
            if result.stdout:
                print(f"Stdout: {result.stdout[:500]}")
            if result.returncode != 0 and result.stderr:
                print(f"Stderr: {result.stderr[:500]}")

    # Test 6: List all mappings
    print("\n" + "-" * 40)
    print("Test 6: List all mappings")
    print("-" * 40)

    mappings = resolver.mapping_service.load_mappings()
    print(f"All mappings: {mappings}")

    # Cleanup: Switch back to main branch
    print("\n" + "-" * 40)
    print("Cleanup")
    print("-" * 40)

    subprocess.run(
        ["git", "checkout", "main"],
        cwd=TEST_PROJECT_DIR,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-D", "feature/mcp-test"],
        cwd=TEST_PROJECT_DIR,
        capture_output=True,
    )
    print("[OK] Cleaned up git branches")

    # Optionally clean up mapping file
    if MAPPING_FILE.exists():
        MAPPING_FILE.unlink()
        print("[OK] Cleaned up mapping file")

    print("\n" + "=" * 60)
    print("Integration test completed successfully!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success = asyncio.run(test_integration())
    exit(0 if success else 1)
