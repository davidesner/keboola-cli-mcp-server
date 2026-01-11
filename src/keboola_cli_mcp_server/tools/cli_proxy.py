"""Generic kbc CLI proxy tool with automatic branch context."""

import subprocess
from fastmcp import FastMCP

from ..config import Settings
from ..services.branch_resolver import BranchResolver, BranchResolutionError, ProjectNotInitializedError


# Whitelist of allowed CLI commands
ALLOWED_COMMANDS = [
    "sync push",
    "sync pull",
    "sync diff",
    "sync init",
    "remote job run",
    "remote table preview",
    "remote table download",
    "remote table upload",
    "remote create bucket",
    "remote create branch",
    "remote list branches",
    "local validate",
    "local create config",
    "local encrypt",
    "status",
]


def _convert_args_to_cli_flags(args: dict | None) -> list[str]:
    """Convert a dictionary of arguments to CLI flags."""
    if not args:
        return []

    flags = []
    for key, value in args.items():
        # Convert snake_case to kebab-case
        flag_name = key.replace("_", "-")

        if isinstance(value, bool):
            if value:
                flags.append(f"--{flag_name}")
        elif isinstance(value, list):
            for item in value:
                flags.extend([f"--{flag_name}", str(item)])
        else:
            flags.extend([f"--{flag_name}", str(value)])

    return flags


def _validate_command(command: str) -> bool:
    """Check if a command is in the allowed list."""
    # Normalize command
    command = command.strip().lower()

    # Check exact matches and prefix matches
    for allowed in ALLOWED_COMMANDS:
        if command == allowed or command.startswith(allowed + " "):
            return True

    return False


def register_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register CLI proxy tools with the MCP server."""

    resolver = BranchResolver(
        working_dir=settings.working_dir,
        mapping_file=settings.get_mapping_file_path(),
        default_branch=settings.git_default_branch,
    )

    @mcp.tool()
    async def kbc(
        command: str,
        args: dict | None = None
    ) -> dict:
        """
        Execute a Keboola CLI command with automatic branch context.

        The current git branch is automatically resolved to its mapped Keboola branch,
        and the KBC_BRANCH_ID environment variable is set accordingly.

        Args:
            command: The kbc command to run (e.g., 'sync push', 'remote table preview')
            args: Optional command arguments as key-value pairs
                  Example: {"dry_run": true, "force": true, "table": "in.c-main.users"}

        Returns:
            Dictionary with success, command, git_branch, keboola_branch_id, output, exit_code

        Raises:
            NO_MAPPING error if current git branch is not linked.
            Use the 'link_branch' tool first to create a mapping.

        Available commands:
            - sync push, sync pull, sync diff, sync init
            - remote job run, remote table preview/download/upload
            - remote create bucket, remote create branch, remote list branches
            - local validate, local create config, local encrypt
            - status
        """
        # Validate command against whitelist
        if not _validate_command(command):
            return {
                "error": "INVALID_COMMAND",
                "message": f"Command '{command}' is not allowed. Available commands: {', '.join(ALLOWED_COMMANDS)}"
            }

        # Resolve branch context
        try:
            async with resolver.branch_context() as (env, branch_info):
                # Build the full command
                cmd_parts = ["/Users/esner/Documents/Prace/KBC/AI-TESTING/keboola-as-code/target/keboola-cli_darwin_arm64_v8.0/kbc"] + command.split()
                cmd_parts.extend(_convert_args_to_cli_flags(args))

                # Execute command
                result = subprocess.run(
                    cmd_parts,
                    cwd=settings.working_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )

                full_command = " ".join(cmd_parts)
                success = result.returncode == 0

                if success:
                    return {
                        "success": True,
                        "command": full_command,
                        "git_branch": branch_info["git_branch"],
                        "keboola_branch_id": branch_info["keboola_branch_id"],
                        "output": result.stdout,
                        "exit_code": result.returncode
                    }
                else:
                    return {
                        "error": "CLI_ERROR",
                        "command": full_command,
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "git_branch": branch_info["git_branch"],
                        "keboola_branch_id": branch_info["keboola_branch_id"]
                    }

        except ProjectNotInitializedError as e:
            return {
                "error": "PROJECT_NOT_INITIALIZED",
                "message": str(e),
                "fix": "Run 'kbc sync init --allow-target-env' to initialize the project properly"
            }
        except BranchResolutionError as e:
            available = list(resolver.mapping_service.load_mappings().keys())
            try:
                git_branch = resolver.get_current_git_branch()
            except Exception:
                git_branch = "unknown"

            return {
                "error": "NO_MAPPING",
                "message": str(e),
                "git_branch": git_branch,
                "available_mappings": available
            }
        except subprocess.TimeoutExpired:
            return {
                "error": "TIMEOUT",
                "message": f"Command '{command}' timed out after 300 seconds"
            }
        except Exception as e:
            return {
                "error": "EXECUTION_ERROR",
                "message": str(e)
            }
