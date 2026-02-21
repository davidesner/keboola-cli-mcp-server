# Keboola CLI MCP Server - Test Project

This is a test Keboola project configured with the Keboola CLI MCP Server in **Proxy Mode**.

Proxy mode provides:
- All remote Keboola MCP tools (SQL workspace, table operations, jobs, etc.)
- Local CLI tools (branch management, kbc commands)
- **Automatic branch resolution per-request** - switching git branches immediately takes effect

## Critical
- Always work in a feature branch (not main/master). The only exception is getting production metadata about jobs, storage, activated flows prior your work in a branch.
- Never run kbc push in main/master branch

### Using CLI with MCP Tools

- **CLI** represents the Keboola project in a file system - use for local editing, validation, and version control
- **MCP tools** operate directly on Keboola via API - use for running jobs, managing tables, getting component schemas

- Use CLI for local editing, validation, and version control
- Use MCP tools for running jobs, getting metadata about storage and tables, and getting component context
- Do not use MCP to get and search configs - CLI local representation has all you need and it's more efficient. 
- The automatic branch context ensures both CLI and MCP tools operate on the correct Keboola branch
- After remote edits via MCP, always run `kbc sync pull` to keep local and remote in sync

#### Branch vs Production Keboola Branches
- Things like answering what tabled and configs are stale or flows unscheduled require access to production (everything in a branch looks stale)
  - To get metadata about table usage, recent jobs you need to look in production.


## Available MCP Tools

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
| `kbc` | Execute Keboola CLI commands with automatic branch context. |

**Available commands:**
- `sync push` - Push local changes to Keboola
- `sync pull` - Pull remote changes from Keboola
- `sync diff` - Show differences between local and remote
- `remote job run` - Run a job
- `remote table preview` - Preview table data
- `remote table download` - Download table data
- `remote table upload` - Upload table data
- `remote create bucket` - Create a new bucket
- `remote create branch` - Create a new development branch
- `local validate` - Validate local configuration
- `status` - Show project status

### Documentation

| Tool | Description |
|------|-------------|
| `search_cli_docs` | Search Keboola CLI documentation. |

## Workflow

### First Time Setup

1. **Check current branch mapping:**
   ```
   Use the get_mapping tool to see if current git branch is linked
   ```

2. **Link branch if needed:**
   ```
   Use the link_branch tool to link git branch to a Keboola development branch
   ```

### Daily Operations

1. **Pull latest changes:**
   ```
   Use kbc tool with command="sync pull"
   ```

2. **Make changes to configurations** (edit files in the project)

3. **Check differences:**
   ```
   Use kbc tool with command="sync diff"
   ```

4. **Push changes:**
   ```
   Use kbc tool with command="sync push"
   ```
   
## Using CLI in combination with Keboola MCP tools

When asked about configurations in project use first the local representation (you need kbc pull first), only if that fails fall back to keboola mcp tools.

CLI represents the Keboola project in a file system. MCP tools operates directly on the Keboola project via API. Using both together allows for a powerful workflow:
- Use CLI for local editing, validation, and version control
- Use MCP tools for running jobs, managing tables, and getting important context about components and their schemas
- The automatic branch context switching ensures that both CLI and MCP tools operate on the correct development branch based on your current git branch
- You have ability to edit configurations remotely using MCP tools and then pull those changes locally using CLI. But use that sparsely, it is more efficient to directly edit the configuration via file structure, run kbc push, and then use MCP tools to run jobs or preview the results.
- When creating a new configuration you can use MCP tools to search appropriate components and get component details, which contains it's schema, get example configurations to understand the structure. Then you can use kbc create config to create the local files and edit the config.json locally. The same goes for updates. The same applies for config rows.
  - If you struggle creating a config locally, you can use the dedicated create_config and update_config MCP tools to create or update configurations remotely, and then pull those changes locally using kbc pull.
= IMPORTANT: after performing edits remotely always pull the changes back to local to keep the local and remote in sync.

### Working with code-based components (SQL, Python, R transformations, Custom Python Application)

These are special types of components that are represented differently than other configurations in the file system. 

- Since the local representation structure is different from the JSON Schema of the configuration. It is recommended to first create a dummy configuration via the MCP tools or via `kbc create config` command, pull and then edit the code files directly.
- For SQL transformations, the SQL code is stored in `.sql` files within the transformation's directory. You can edit these files directly and push changes using `kbc sync push`.
- For Python and R transformations, the code is stored in `.py` or `.r` files respectively. Edit these files as needed and push changes with `kbc sync push`.
- For Custom Python Applications, the application code is stored in the `application` directory. You can modify the code file directly and use `kbc sync push` to update the application in Keboola.
- Custom Python applications that contain credentials in the user_properties parameter cannot be executed locally unless you replace those credentials in plain text. To test such applications use the MCP tool to run the application remotely.
  - The changes can still be done locally and pushed using `kbc sync push`. It is more context efficient to edit the code locally and push, rather than editing remotely.


## SQL Transformations

Because you are working in branches, the transformations cannot work with direct RO access using full db identifiers. 
The branching system in Keboola automatically creates a branched version of each table in a new schema. E.g. if you run a job that writes to table out.c-bucket.table_a, 
the resulting path will be out.c-BRANCH_ID-bucket.table_a. You can query this table directly using it's FQN but it cannot be used in transformation code, as it would not be valid after the branch is merged to production.

- Listing tables and bucket via MCP tools returns always the correct FQN (i.e. if a branched version of the table exists, it will return the branched version, otherwise the production one).
- Input mapping in Transformations always need to have the bucket/table id that is production (these are also always properly returned by the MCP).
    - The platform itself handles automatic defference between production and branched tables when using input/output mapping. This is why in branch you need to use input mappings.

## Handling Schema Changes

- Keboola platform can automatically add new columns to existing tables when running a job.
- If a column name changes or is removed, the job will fail. The only way to handle this is dropping the table and running the job again.
  - Before a first write into a table in a branch, you can change the schema because a new branched table will be created. After the first write, the schema is locked and can only be changed by dropping the table.
- Branched tables can be safely dropped. Never drop production tables.

## Deleting configurations
- In a branch you can delete a configuration by deleting them from the project representation (related folders) and running kbc push --force
- This will not delete the configuration from the production branch, but it will be deleted from the branch you are working on. 


## Branch Context

The MCP server automatically:
- Detects the current git branch
- Looks up the corresponding Keboola branch ID from `branch-mapping.json`
- Sets `KBC_BRANCH_ID` environment variable for all CLI commands

This ensures you always work with the correct Keboola development branch.

## Creating commits, PRs

- Make sure to always kbc pull the latest changes before starting or finishing the work.
- After finishing the work, run kbc sync push to push the changes to Keboola.
- Create a commit with a meaningful message describing the changes.
- 

## Error Handling

### NO_MAPPING Error
If you see this error, use `link_branch` tool first to create a mapping.

### PROJECT_NOT_INITIALIZED Error
The project must be initialized with `--allow-target-env` flag. Run:
```bash
kbc sync init --allow-target-env --storage-api-host connection.<region>.keboola.com
```

## Project Structure

```
test-kbc-project/
├── .keboola/
│   └── manifest.json      # Project manifest (allowTargetEnv must be true)
├── .mcp.json              # MCP server configuration
├── .env.local             # Storage API token (gitignored)
├── branch-mapping.json    # Git-to-Keboola branch mappings
├── main/                  # Main branch configurations
│   ├── application/       # Application configurations
│   ├── extractor/         # Extractor configurations
│   └── transformation/    # Transformation configurations
└── CLAUDE.md              # This file
```

## Tips

- Always check `get_mapping` before starting work to confirm branch context
- Use `sync diff` before `sync push` to review changes
- The `branch-mapping.json` file is local and gitignored - each developer has their own mappings
- Main/master git branches map to Keboola production (no branch override)