# Keboola CLI MCP Server - Development Instructions

## Project Overview

Build an MCP (Model Context Protocol) server that acts as a **deterministic proxy** for Keboola CLI (`kbc`) operations, with automatic git-to-Keboola branch mapping. The server ensures agents cannot accidentally use the wrong Keboola branch by enforcing branch resolution before any CLI command execution.

## Core Requirements

### Technology Stack
- **Language**: Python 3.10+
- **MCP Framework**: FastMCP library
- **Transport**: stdio only (local execution required for CLI access)
- **Architecture**: Inspired by https://github.com/keboola/mcp-server, the code is available locally in /Users/esner/Documents/Prace/KBC/AI-TESTING/keboola-mcp-server

### Key Principles
1. **Deterministic branch resolution**: Always derive the current git branch programmatically, never infer
2. **Fail-safe CLI proxy**: All CLI commands must go through branch resolution; fail if no mapping exists
3. **Single source of truth**: `branch-mapping.json` is the authoritative mapping file

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Keboola CLI MCP Server                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Branch Tools   │  │   CLI Proxy     │  │   Documentation │ │
│  │                 │  │                 │  │                 │ │
│  │ • link_branch   │  │ • kbc           │  │ • search_docs   │ │
│  │ • unlink_branch │  │   (generic      │  │   (from RAG)    │ │
│  │ • get_mapping   │  │    proxy)       │  │                 │ │
│  │ • list_mappings │  │                 │  │                 │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │          │
│           ▼                    ▼                    ▼          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Branch Resolution Layer                        ││
│  │  1. Run: git branch --show-current                          ││
│  │  2. Lookup in branch-mapping.json                           ││
│  │  3. If no mapping → ERROR (force link_branch first)         ││
│  │  4. If mapping exists → Set KBC_BRANCH_ID env var           ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│           ┌──────────────────┼──────────────────┐              │
│           ▼                  ▼                  ▼              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │ branch-mapping  │  │  kbc CLI         │  │ Keboola API  │   │
│  │ .json           │  │  (subprocess)    │  │ (for docs)   │   │
│  └─────────────────┘  └──────────────────┘  └──────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
keboola-cli-mcp-server/
├── pyproject.toml
├── README.md
├── src/
│   └── keboola_cli_mcp_server/
│       ├── __init__.py
│       ├── __main__.py              # Entry point
│       ├── server.py                # FastMCP server setup
│       ├── config.py                # Configuration management
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── branch.py            # Branch management tools
│       │   ├── cli_proxy.py         # Generic kbc CLI proxy
│       │   └── docs.py              # Documentation search (ported from keboola/mcp-server)
│       ├── services/
│       │   ├── __init__.py
│       │   ├── git.py               # Git operations
│       │   ├── branch_mapping.py    # Mapping file management
│       │   ├── branch_resolver.py   # Core resolution logic
│       │   └── sapi_client.py       # Storage API client (copy from keboola/mcp-server)
│       └── models/
│           ├── __init__.py
│           └── schemas.py           # Pydantic models
└── tests/
    ├── __init__.py
    ├── test_branch_tools.py
    ├── test_cli_proxy.py
    └── test_branch_resolver.py
```

---

## Environment Variables

The server requires these environment variables:

```bash
# Required
KBC_STORAGE_API_TOKEN=<your-storage-api-token>
KBC_STORAGE_API_HOST=connection.<region>.keboola.com
GIT_DEFAULT_BRANCH=main  # or master, depending on your repo. This is needed because main/master maps to production branch, which in turn has no mapping. 
# So no branch mapping is allowed only for default branch. In such case there is no KBC_BRANCH_ID ovrerride.
```

---

## Tool Specifications

### 1. Branch Management Tools

#### `link_branch`
Links the current git branch to a Keboola development branch. **Creates a new Keboola branch if needed.**

```python
@mcp.tool()
async def link_branch(
    branch_name: str | None = None,
    description: str | None = None
) -> dict:
    """
    Links the current git branch to a Keboola development branch.
    
    If no Keboola branch with the specified name exists, creates one.
    The Keboola branch name defaults to the git branch name if not specified.
    
    Args:
        branch_name: Optional custom name for the Keboola branch (defaults to git branch name)
        description: Optional description for the new Keboola branch
    
    Returns:
        {
            "git_branch": "feature/auth",
            "keboola_branch_id": "972851",
            "keboola_branch_name": "feature/auth",
            "created": true,
            "message": "Successfully linked and created Keboola branch"
        }
    
    Raises:
        Error if not in a git repository
        Error if on main/master branch (should use production, not dev branch)
    """
```

**Implementation notes:**
- Use `kbc remote create branch -n <name> --output-json <tempfile>` to create the branch
- Parse the output JSON to get the branch ID
- Update `branch-mapping.json` atomically
- If git branch is `main` or `master`, map to `null` (production branch)

#### `unlink_branch`
Removes the mapping for the current git branch.

```python
@mcp.tool()
async def unlink_branch() -> dict:
    """
    Removes the branch mapping for the current git branch.
    
    Does NOT delete the Keboola development branch - only removes the local mapping.
    Use the Keboola UI or API to delete the branch if needed.
    
    Returns:
        {
            "git_branch": "feature/auth",
            "unlinked_keboola_branch_id": "972851",
            "message": "Mapping removed. Keboola branch still exists."
        }
    """
```

#### `get_mapping`
Gets the mapping status for the current git branch.

```python
@mcp.tool()
async def get_mapping() -> dict:
    """
    Gets the Keboola branch mapping for the current git branch.
    
    This is a safe, read-only operation that always succeeds.
    
    Returns:
        {
            "git_branch": "feature/auth",
            "keboola_branch_id": "972851" | null,
            "linked": true,
            "is_production": false
        }
    """
```

#### `list_mappings`
Lists all branch mappings.

```python
@mcp.tool()
async def list_mappings() -> dict:
    """
    Lists all git-to-Keboola branch mappings.
    
    Returns:
        {
            "mappings": {
                "main": null,
                "feature/auth": "972851",
                "feature/pipeline": "983421"
            },
            "current_git_branch": "feature/auth"
        }
    """
```

---

### 2. CLI Proxy Tool

#### `kbc`
Generic proxy for all Keboola CLI commands with automatic branch context.

```python
ALLOWED_COMMANDS = [
    "sync push", "sync pull", "sync diff", "sync init",
    "remote job run", "remote table preview", "remote table download",
    "remote table upload", "remote create bucket",
    "local validate", "local create config", "local encrypt",
    "status"
]

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
        {
            "success": true,
            "command": "kbc sync push --dry-run",
            "git_branch": "feature/auth",
            "keboola_branch_id": "972851",
            "output": "...",
            "exit_code": 0
        }
    
    Raises:
        NO_MAPPING error if current git branch is not linked.
        Use the 'link_branch' tool first to create a mapping.
    
    Available commands:
        - sync push, sync pull, sync diff, sync init
        - remote job run, remote table preview/download/upload
        - remote create bucket
        - local validate, local create config, local encrypt
        - status
    """
```

**Implementation notes:**
- Validate command against `ALLOWED_COMMANDS` whitelist
- Convert `args` dict to CLI flags (e.g., `{"dry_run": True}` → `--dry-run`)
- Always run through `with_branch_context()` wrapper
- Capture stdout, stderr, and exit code

---

### 3. Documentation Tool

#### `search_cli_docs`
Ported from `docs_query` in https://github.com/keboola/mcp-server/blob/main/src/keboola_mcp_server/tools/doc.py

```python
@mcp.tool()
async def search_cli_docs(query: str) -> dict:
    """
    Search Keboola CLI documentation for commands, flags, environment variables, and workflows.
    
    Use this to find information about kbc commands like sync, push, pull, remote, local,
    branch management, environment variables (KBC_BRANCH_ID, KBC_STORAGE_API_TOKEN), and DevOps workflows.
    
    Args:
        query: Search query (e.g., 'how to push changes', 'branch environment variables', 'sync init flags')
    
    Returns:
        {
            "results": [...],
            "query": "Keboola CLI kbc command: <original query>"
        }
    """
```

**Implementation notes:**
- Port the `docs_query` function from keboola/mcp-server
- Prefix all queries with `"Keboola CLI kbc command: "` to scope RAG results to CLI content
- Reuse the existing SAPI client for API calls

---

## Core Services Implementation

### Branch Resolution Layer

```python
# src/keboola_cli_mcp_server/services/branch_resolver.py

import subprocess
import json
from pathlib import Path
from typing import TypeVar, Callable, Awaitable
from contextlib import asynccontextmanager

T = TypeVar('T')

class BranchResolutionError(Exception):
    """Raised when branch mapping is not found."""
    pass

class BranchResolver:
    def __init__(self, working_dir: Path, mapping_file: Path):
        self.working_dir = working_dir
        self.mapping_file = mapping_file
    
    def get_current_git_branch(self) -> str:
        """Get the current git branch name."""
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    
    def load_mappings(self) -> dict[str, str | None]:
        """Load branch mappings from file."""
        if not self.mapping_file.exists():
            return {}
        return json.loads(self.mapping_file.read_text())
    
    def save_mappings(self, mappings: dict[str, str | None]) -> None:
        """Save branch mappings to file atomically."""
        temp_file = self.mapping_file.with_suffix('.tmp')
        temp_file.write_text(json.dumps(mappings, indent=2))
        temp_file.rename(self.mapping_file)
    
    def get_keboola_branch_id(self, git_branch: str) -> str | None:
        """
        Get the Keboola branch ID for a git branch.
        
        Returns:
            Branch ID string, or None for production (main/master)
        
        Raises:
            BranchResolutionError if no mapping exists
        """
        mappings = self.load_mappings()
        
        if git_branch not in mappings:
            raise BranchResolutionError(
                f'NO_MAPPING: Git branch "{git_branch}" is not linked to any Keboola branch. '
                f'Use the "link_branch" tool first.'
            )
        
        return mappings[git_branch]
    
    @asynccontextmanager
    async def branch_context(self):
        """
        Context manager that provides environment with correct KBC_BRANCH_ID.
        
        Usage:
            async with resolver.branch_context() as (env, branch_info):
                result = subprocess.run(["kbc", "sync", "push"], env=env)
        """
        import os
        
        git_branch = self.get_current_git_branch()
        keboola_branch_id = self.get_keboola_branch_id(git_branch)
        
        env = os.environ.copy()
        
        if keboola_branch_id is not None:
            env["KBC_BRANCH_ID"] = keboola_branch_id
        elif "KBC_BRANCH_ID" in env:
            # Production branch - ensure no branch ID is set
            del env["KBC_BRANCH_ID"]
        
        branch_info = {
            "git_branch": git_branch,
            "keboola_branch_id": keboola_branch_id,
            "is_production": keboola_branch_id is None
        }
        
        yield env, branch_info
```

### Branch Creation via CLI

```python
# src/keboola_cli_mcp_server/services/branch_mapping.py

import subprocess
import json
import tempfile
from pathlib import Path

class BranchCreationError(Exception):
    pass

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
        description: Optional description
        working_dir: Working directory for CLI execution
    
    Returns:
        {"id": "972851", "name": "feature/auth", ...}
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_file = Path(f.name)
    
    try:
        cmd = ["kbc", "remote", "create", "branch", "-n", branch_name]
        
        if description:
            cmd.extend(["--description", description])
        
        cmd.extend(["--output-json", str(output_file)])
        
        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise BranchCreationError(
                f"Failed to create Keboola branch: {result.stderr}"
            )
        
        # Parse the output JSON to get branch details
        branch_data = json.loads(output_file.read_text())
        return branch_data
        
    finally:
        output_file.unlink(missing_ok=True)
```

---

## Mapping File Schema

`branch-mapping.json`:

```json
{
  "main": null,
  "master": null,
  "feature/auth": "972851",
  "feature/data-pipeline": "983421",
  "bugfix/fix-extraction": "983422"
}
```

- Key: git branch name
- Value: Keboola branch ID (string) or `null` for production
- `null` means "use production branch, don't set KBC_BRANCH_ID"

---

## Server Entry Point

```python
# src/keboola_cli_mcp_server/server.py

from fastmcp import FastMCP
from .tools import branch, cli_proxy, docs
from .config import Settings

def create_server() -> FastMCP:
    settings = Settings()
    
    mcp = FastMCP(
        name="keboola-cli",
        description="Keboola CLI MCP Server - Deterministic branch-aware CLI proxy"
    )
    
    # Register tools
    branch.register_tools(mcp, settings)
    cli_proxy.register_tools(mcp, settings)
    docs.register_tools(mcp, settings)
    
    return mcp

# src/keboola_cli_mcp_server/__main__.py

from .server import create_server

def main():
    server = create_server()
    server.run(transport="stdio")

if __name__ == "__main__":
    main()
```

---

## Error Handling

### NO_MAPPING Error
When a CLI command is attempted without a branch mapping:

```python
{
    "error": "NO_MAPPING",
    "message": "Git branch 'feature/new-thing' is not linked to any Keboola branch. Use the 'link_branch' tool first.",
    "git_branch": "feature/new-thing",
    "available_mappings": ["main", "feature/auth"]
}
```

### CLI Execution Error
When a CLI command fails:

```python
{
    "error": "CLI_ERROR",
    "command": "kbc sync push",
    "exit_code": 1,
    "stdout": "...",
    "stderr": "...",
    "git_branch": "feature/auth",
    "keboola_branch_id": "972851"
}
```

---

## Code to Port from keboola/mcp-server

Copy and adapt these files from https://github.com/keboola/mcp-server:

1. **SAPI Client**: `src/keboola_mcp_server/client/` → `src/keboola_cli_mcp_server/services/sapi_client.py`
   - Needed for docs search and potentially direct API calls

2. **Docs Tool**: `src/keboola_mcp_server/tools/doc.py` → `src/keboola_cli_mcp_server/tools/docs.py`
   - Modify tool description to focus on CLI documentation
   - Prefix queries with `"Keboola CLI kbc command: "` to scope results

3. **Config patterns**: `src/keboola_mcp_server/config.py` → `src/keboola_cli_mcp_server/config.py`
   - Adapt settings/configuration patterns

---

## Testing Strategy

### Unit Tests
- Test `BranchResolver` with mock git/file operations
- Test mapping file read/write atomicity
- Test CLI argument formatting

### Integration Tests
- Test actual git branch detection
- Test CLI command execution (with mock kbc)
- Test branch creation flow

### Test Fixtures
```python
@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmp_path, check=True)
    return tmp_path

@pytest.fixture
def mock_mapping_file(tmp_path):
    """Create a temporary mapping file."""
    mapping_file = tmp_path / "branch-mapping.json"
    mapping_file.write_text('{"main": null, "feature/test": "12345"}')
    return mapping_file
```

---

## Usage Example

Once implemented, the server enables this workflow:

```
User: "Push my changes to Keboola"

Agent: [calls kbc(command="sync push")]
       ↓
Server: BranchResolver.branch_context()
        → git branch --show-current → "feature/auth"
        → lookup mapping → NOT FOUND
        → Return NO_MAPPING error
       ↓
Agent: "I need to link this branch first"
       [calls link_branch()]
       ↓
Server: → Creates Keboola branch via CLI
        → Saves mapping to branch-mapping.json
        → Returns success with branch ID
       ↓
Agent: "Now I can push"
       [calls kbc(command="sync push")]
       ↓
Server: → Resolves branch → "972851"
        → Sets KBC_BRANCH_ID=972851
        → Runs: kbc sync push
        → Returns success
```

---

## Dependencies (pyproject.toml)

```toml
[project]
name = "keboola-cli-mcp-server"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastmcp>=0.1.0",
    "pydantic>=2.0",
    "httpx>=0.25.0",  # For SAPI client
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]

[project.scripts]
keboola-cli-mcp = "keboola_cli_mcp_server.__main__:main"
```

---

## References

- **Keboola MCP Server** (architecture inspiration): https://github.com/keboola/mcp-server
- **Keboola CLI Documentation**: https://developers.keboola.com/cli/
- **CLI Commands Reference**: https://developers.keboola.com/cli/commands/
- **Branch Management**: https://developers.keboola.com/cli/commands/remote/create/branch/
- **DevOps Use Cases** (KBC_BRANCH_ID usage): https://developers.keboola.com/cli/devops-use-cases/
- **Storage API** (for SAPI client): https://keboola.docs.apiary.io/
- **FastMCP Documentation**: https://github.com/jlowin/fastmcp

---

## Development Checklist

- [ ] Set up project structure with pyproject.toml
- [ ] Implement `BranchResolver` service
- [ ] Implement `branch-mapping.json` file management
- [ ] Implement `link_branch` tool (with Keboola branch creation)
- [ ] Implement `unlink_branch` tool
- [ ] Implement `get_mapping` tool
- [ ] Implement `list_mappings` tool
- [ ] Implement `kbc` generic CLI proxy tool
- [ ] Port SAPI client from keboola/mcp-server
- [ ] Port and adapt `docs_query` tool
- [ ] Add comprehensive error handling
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Add README with usage instructions