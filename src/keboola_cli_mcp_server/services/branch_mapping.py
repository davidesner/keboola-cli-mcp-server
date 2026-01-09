"""Branch mapping file management service."""

import json
import subprocess
from pathlib import Path


class BranchCreationError(Exception):
    """Raised when Keboola branch creation fails."""
    pass


class BranchMappingService:
    """Service for managing branch-mapping.json file."""

    def __init__(self, mapping_file: Path):
        self.mapping_file = mapping_file

    def load_mappings(self) -> dict[str, str | None]:
        """Load branch mappings from file."""
        if not self.mapping_file.exists():
            return {}
        try:
            return json.loads(self.mapping_file.read_text())
        except json.JSONDecodeError:
            return {}

    def save_mappings(self, mappings: dict[str, str | None]) -> None:
        """Save branch mappings to file atomically."""
        # Ensure parent directory exists
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file then rename for atomicity
        temp_file = self.mapping_file.with_suffix('.tmp')
        temp_file.write_text(json.dumps(mappings, indent=2))
        temp_file.rename(self.mapping_file)

    def add_mapping(self, git_branch: str, keboola_branch_id: str | None) -> None:
        """Add or update a branch mapping."""
        mappings = self.load_mappings()
        mappings[git_branch] = keboola_branch_id
        self.save_mappings(mappings)

    def remove_mapping(self, git_branch: str) -> str | None:
        """Remove a branch mapping. Returns the removed keboola_branch_id or None."""
        mappings = self.load_mappings()
        keboola_branch_id = mappings.pop(git_branch, None)
        self.save_mappings(mappings)
        return keboola_branch_id

    def get_mapping(self, git_branch: str) -> str | None:
        """Get the Keboola branch ID for a git branch."""
        mappings = self.load_mappings()
        return mappings.get(git_branch)

    def has_mapping(self, git_branch: str) -> bool:
        """Check if a git branch has a mapping."""
        mappings = self.load_mappings()
        return git_branch in mappings


async def create_keboola_branch(
    branch_name: str,
    description: str | None = None,
    working_dir: Path | None = None
) -> dict:
    """
    Create a new Keboola development branch using the CLI.

    Uses: kbc remote create branch -n <name> --output-json <file>

    Args:
        branch_name: Name for the new Keboola branch
        description: Optional description (not used - kbc doesn't support it)
        working_dir: Working directory for CLI execution

    Returns:
        {"id": "972851", "name": "branch_name", ...}
    """
    import uuid

    # kbc --output-json uses paths relative to working_dir, so create output file there
    cwd = working_dir or Path.cwd()
    output_filename = f".branch-create-{uuid.uuid4().hex[:8]}.json"
    output_file = cwd / output_filename

    try:
        cmd = ["kbc", "remote", "create", "branch", "-n", branch_name, "--output-json", output_filename]

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True
        )

        # Check if output file was created with branch info
        if output_file.exists():
            try:
                output_data = json.loads(output_file.read_text())
                # The output contains "newBranchId" key
                branch_id = output_data.get("newBranchId") or output_data.get("id")
                if branch_id:
                    return {
                        "id": str(branch_id),
                        "name": branch_name,
                        "path": branch_name
                    }
            except json.JSONDecodeError:
                pass  # Fall through to error handling

        # If we didn't get the branch ID from output file, check the error
        if result.returncode != 0:
            raise BranchCreationError(
                f"Failed to create Keboola branch: {result.stderr or result.stdout}"
            )

        raise BranchCreationError(
            f"Branch may have been created but could not capture ID. Output: {result.stdout}"
        )

    finally:
        # Clean up output file
        if output_file.exists():
            output_file.unlink()


async def find_keboola_branch_by_name(
    branch_name: str,
    working_dir: Path | None = None
) -> dict | None:
    """
    Find an existing Keboola branch by name using the local manifest.

    Note: kbc transforms "/" to "-" in branch paths, so we check both.

    Returns:
        Branch info dict if found, None otherwise
    """
    try:
        manifest_file = (working_dir or Path.cwd()) / ".keboola" / "manifest.json"
        if not manifest_file.exists():
            return None

        manifest = json.loads(manifest_file.read_text())
        # Try exact match and transformed name (/ -> -)
        search_names = [branch_name, branch_name.replace("/", "-")]
        for branch in manifest.get("branches", []):
            if branch.get("path") in search_names:
                return {
                    "id": str(branch.get("id")),
                    "name": branch_name,
                    "path": branch.get("path")
                }
        return None

    except (json.JSONDecodeError, FileNotFoundError):
        return None
