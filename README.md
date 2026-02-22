# Keboola CLI MCP Server

A Model Context Protocol (MCP) server that acts as a deterministic proxy for Keboola CLI (`kbc`) operations, with automatic git-to-Keboola branch mapping.

## Overview

This server ensures agents cannot accidentally use the wrong Keboola branch by enforcing branch resolution before any CLI command execution. It provides:

- **Deterministic branch resolution**: Always derives the current git branch programmatically
- **Fail-safe CLI proxy**: All CLI commands must go through branch resolution
- **Single source of truth**: `branch-mapping.json` is the authoritative mapping file
- **Project validation**: Ensures the Keboola project is properly initialized with `--allow-target-env`

## Server Modes

The server supports two modes:

### CLI Mode (Default)

Provides local CLI tools for running `kbc` commands with automatic branch context:
- Branch management (link_branch, unlink_branch, etc.)
- CLI proxy for kbc commands (sync push, sync pull, etc.)
- Documentation search

### Proxy Mode

Proxies to the remote Keboola MCP server with automatic `X-Branch-Id` header injection:
- **All remote Keboola MCP tools** (SQL workspace, table operations, jobs, etc.)
- **Plus local CLI tools** (branch management, kbc commands)
- **Dynamic branch resolution per-request** - switching git branches immediately takes effect

Enable with: `KBC_MCP_PROXY_MODE=true`

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Proxy Mode Flow                              │
│                                                                      │
│  1. Claude calls any tool (e.g., "sql_query")                       │
│                    │                                                 │
│                    ▼                                                 │
│  2. client_factory() called  ◄── PER REQUEST                        │
│       ├── git branch --show-current → "feature/billing"             │
│       ├── branch-mapping.json → "22750"                             │
│       └── Headers: X-StorageAPI-Token, X-Branch-Id: 22750           │
│                    │                                                 │
│                    ▼                                                 │
│  3. Request forwarded to remote Keboola MCP server                  │
│     https://mcp-agent.{stack}.keboola.com/mcp                       │
│                    │                                                 │
│                    ▼                                                 │
│  4. Response returned to Claude                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **Keboola CLI (`kbc`)** must be installed and available in your PATH
   - Install from: https://developers.keboola.com/cli/

2. **Keboola project must be initialized with `--allow-target-env`**
   ```bash
   kbc sync init --allow-target-env --storage-api-host connection.<region>.keboola.com
   ```
   This flag is **required** for the `KBC_BRANCH_ID` environment variable override to work.

3. **Python 3.10+**

## Installation

```bash
# Clone and install
git clone <repository>
cd keboola-cli-mcp-server
pip install -e .
```

## Configuration

### Environment Variables

Create a `.env.local` file in your Keboola project directory:

```bash
# Required - Keboola Storage API token
KBC_STORAGE_API_TOKEN=<your-storage-api-token>

# Required - Storage API host (without protocol, used to derive MCP server URL in proxy mode)
KBC_STORAGE_API_HOST=connection.<region>.keboola.com

# Optional - defaults shown
GIT_DEFAULT_BRANCH=main          # Default branch name (maps to production)
KBC_WORKING_DIR=.                # Working directory for CLI operations
KBC_MAPPING_FILE=branch-mapping.json  # Path to mapping file

# Proxy mode - enable to get remote Keboola MCP tools with branch injection
KBC_MCP_PROXY_MODE=false         # Set to "true" to enable proxy mode
```

### MCP Client Setup

#### Claude Desktop

Add to your `claude_desktop_config.json`:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "keboola-cli": {
      "command": "python",
      "args": ["-m", "keboola_cli_mcp_server"],
      "cwd": "/path/to/your/keboola-project",
      "env": {
        "KBC_STORAGE_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

#### Cursor

Add to your `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "keboola-cli": {
      "command": "python",
      "args": ["-m", "keboola_cli_mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "KBC_STORAGE_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

#### Claude Code (CLI)

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "keboola-cli": {
      "command": "python",
      "args": ["-m", "keboola_cli_mcp_server"],
      "env": {
        "KBC_STORAGE_API_TOKEN": "your-token-here",
        "KBC_STORAGE_API_HOST": "connection.keboola.com"
      }
    }
  }
}
```

#### Proxy Mode Configuration

To enable proxy mode (recommended for full Keboola MCP functionality):

```json
{
  "mcpServers": {
    "keboola-unified": {
      "command": "python",
      "args": ["-m", "keboola_cli_mcp_server"],
      "env": {
        "KBC_STORAGE_API_TOKEN": "your-token-here",
        "KBC_STORAGE_API_HOST": "connection.keboola.com",
        "KBC_MCP_PROXY_MODE": "true"
      }
    }
  }
}
```

This gives you access to:
- All remote Keboola MCP tools (SQL workspace, table operations, etc.)
- Local CLI tools (branch management, kbc commands)
- Automatic branch resolution per-request

## Available Tools

### Branch Management

| Tool | Description |
|------|-------------|
| `link_branch` | Links current git branch to a Keboola development branch. Creates new branch if needed. |
| `unlink_branch` | Removes the mapping for the current git branch (does not delete the Keboola branch). |
| `get_mapping` | Gets the mapping status for the current git branch. |
| `list_mappings` | Lists all git-to-Keboola branch mappings. |

### CLI Proxy

| Tool | Description |
|------|-------------|
| `kbc` | Execute any allowed Keboola CLI command with automatic branch context. |

**Allowed commands:**
- `sync push`, `sync pull`, `sync diff`, `sync init`
- `remote job run`, `remote table preview/download/upload`
- `remote create bucket`, `remote create branch`, `remote list branches`
- `local validate`, `local create config`, `local encrypt`
- `status`

### Documentation

| Tool | Description |
|------|-------------|
| `search_cli_docs` | Search Keboola CLI documentation for commands, flags, and workflows. |

## Usage Example

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

## Error Handling

### PROJECT_NOT_INITIALIZED

```json
{
  "error": "PROJECT_NOT_INITIALIZED",
  "message": "PROJECT_MISCONFIGURED: The project was not initialized with --allow-target-env flag.",
  "fix": "Run 'kbc sync init --allow-target-env' to initialize the project properly"
}
```

**Solution**: Re-initialize your Keboola project with:
```bash
kbc sync init --allow-target-env --storage-api-host connection.<region>.keboola.com
```

### NO_MAPPING

```json
{
  "error": "NO_MAPPING",
  "message": "Git branch 'feature/new-thing' is not linked to any Keboola branch.",
  "git_branch": "feature/new-thing",
  "available_mappings": ["main", "feature/auth"]
}
```

**Solution**: Use the `link_branch` tool first to create a mapping.

## Running the Server

```bash
# Run via stdio transport (default)
python -m keboola_cli_mcp_server

# Or use the entry point
keboola-cli-mcp
```

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Project Structure

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
│       │   ├── branch.py            # Branch management tools
│       │   ├── cli_proxy.py         # Generic kbc CLI proxy
│       │   └── docs.py              # Documentation search
│       ├── services/
│       │   ├── git.py               # Git operations
│       │   ├── branch_mapping.py    # Mapping file management
│       │   ├── branch_resolver.py   # Core resolution logic
│       │   └── sapi_client.py       # Storage API client
│       └── models/
│           └── schemas.py           # Pydantic models
└── tests/
    ├── test_branch_resolver.py
    ├── test_cli_proxy.py
    └── test_branch_tools.py
```

## Branch Mapping File

The `branch-mapping.json` file stores git-to-Keboola branch mappings:

```json
{
  "main": null,
  "feature/auth": "972851",
  "feature/data-pipeline": "983421"
}
```

- **Key**: git branch name
- **Value**: Keboola branch ID (string) or `null` for production
- `null` means "use production branch, don't set KBC_BRANCH_ID"

**Note**: This file should be added to `.gitignore` as mappings may differ per developer.

## How Branch Resolution Works

1. **Git branch detection**: Runs `git branch --show-current` to get current branch
2. **Mapping lookup**: Checks `branch-mapping.json` for a mapping
3. **Default branch handling**: `main`/`master` branches map to production (no `KBC_BRANCH_ID` override)
4. **Environment setup**: Sets `KBC_BRANCH_ID` for non-production branches
5. **CLI execution**: Runs `kbc` command with the prepared environment

This ensures that when you're on `feature/auth` git branch mapped to Keboola branch `972851`, all CLI operations target that specific development branch.

## License

MIT
