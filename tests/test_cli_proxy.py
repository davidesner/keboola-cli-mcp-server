"""Tests for CLI proxy tool."""

import pytest

from keboola_cli_mcp_server.tools.cli_proxy import (
    _convert_args_to_cli_flags,
    _validate_command,
    ALLOWED_COMMANDS,
)


class TestConvertArgsToCliFlags:
    def test_empty_args(self):
        """Test with no arguments."""
        assert _convert_args_to_cli_flags(None) == []
        assert _convert_args_to_cli_flags({}) == []

    def test_boolean_true_flag(self):
        """Test boolean true value becomes flag."""
        result = _convert_args_to_cli_flags({"dry_run": True})
        assert result == ["--dry-run"]

    def test_boolean_false_flag(self):
        """Test boolean false value is omitted."""
        result = _convert_args_to_cli_flags({"dry_run": False})
        assert result == []

    def test_string_value(self):
        """Test string value becomes flag with value."""
        result = _convert_args_to_cli_flags({"table": "in.c-main.users"})
        assert result == ["--table", "in.c-main.users"]

    def test_snake_case_to_kebab(self):
        """Test snake_case is converted to kebab-case."""
        result = _convert_args_to_cli_flags({"output_json": "/tmp/out.json"})
        assert result == ["--output-json", "/tmp/out.json"]

    def test_list_value(self):
        """Test list value becomes multiple flags."""
        result = _convert_args_to_cli_flags({"columns": ["id", "name"]})
        assert result == ["--columns", "id", "--columns", "name"]

    def test_multiple_args(self):
        """Test multiple arguments."""
        result = _convert_args_to_cli_flags({
            "dry_run": True,
            "force": True,
            "table": "in.c-main.users",
        })
        assert "--dry-run" in result
        assert "--force" in result
        assert "--table" in result
        assert "in.c-main.users" in result


class TestValidateCommand:
    def test_allowed_commands(self):
        """Test all allowed commands pass validation."""
        for cmd in ALLOWED_COMMANDS:
            assert _validate_command(cmd), f"Command '{cmd}' should be allowed"

    def test_allowed_command_with_extra_args(self):
        """Test allowed commands with additional args."""
        assert _validate_command("sync push --dry-run")
        assert _validate_command("remote table preview in.c-main.users")

    def test_disallowed_command(self):
        """Test disallowed commands fail validation."""
        assert not _validate_command("rm -rf /")
        assert not _validate_command("status;rm -rf /")
        assert not _validate_command("remote delete branch")

    def test_case_insensitive(self):
        """Test command validation is case insensitive."""
        assert _validate_command("SYNC PUSH")
        assert _validate_command("Sync Pull")

    def test_partial_match_not_allowed(self):
        """Test partial matches are not allowed."""
        assert not _validate_command("syn")
        assert not _validate_command("remote")
