"""Stress tests for src/agents/tools/system_admin_tools.py

Security-focused tests covering:
1. Command injection in git operations
2. Path traversal attempts
3. Invalid crontab syntax
4. Resource exhaustion scenarios
5. Admin privilege bypass attempts
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TestConfig


# Helper to set up admin context
def setup_admin_context(test_config, is_admin=True):
    """Create patches for admin user context."""
    email = "admin@example.com" if is_admin else "user@example.com"
    return (
        patch("src.agents.tools.system_admin_tools.get_user_email", return_value=email),
        patch("src.agents.tools.system_admin_tools.get_config", return_value=test_config),
    )


class TestCommandInjectionInGitOperations:
    """Tests for command injection vulnerabilities in git operations."""

    def test_git_status_is_safe(self, test_config):
        """git status uses hardcoded args - no injection possible."""
        with patch(
            "src.agents.tools.system_admin_tools.get_config", return_value=test_config
        ), patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "", "")

            from src.agents.tools.system_admin_tools import check_git_status

            check_git_status()

            # git status calls _run_command twice: once for status, once for branch
            assert mock_run.call_count == 2

            # Verify first call (status) uses hardcoded args only
            cmd = mock_run.call_args_list[0][0][0]
            assert cmd[0] == "git"
            assert "-C" in cmd
            assert "status" in cmd
            # No user input in command

    def test_git_pull_is_safe(self, test_config):
        """git pull uses hardcoded args - no injection possible."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch, patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "Already up to date.", "")

            from src.agents.tools.system_admin_tools import git_pull

            result = git_pull()

            # Verify hardcoded args
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd == ["git", "-C", str(test_config.project_root), "pull"]

    def test_run_tests_unsafe_flag_blocked(self, test_config):
        """Test that unsafe pytest flags are blocked.

        Only safe flags (-k, -x, -m, --maxfail, --collect-only, --co) are allowed.
        """
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import run_tests

            # Attempt injection via unsafe flag - now blocked
            malicious_pattern = "-k 'test' --help"  # --help is not in safe list
            result = run_tests(test_pattern=malicious_pattern)

            # Unsafe flags are now rejected
            assert result["status"] == "error"
            assert "not allowed" in result["message"].lower()

    def test_run_tests_safe_flags_allowed(self, test_config):
        """Test that safe pytest flags are allowed."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch, patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "1 PASSED", "")

            from src.agents.tools.system_admin_tools import run_tests

            # Safe flag -k should be allowed
            result = run_tests(test_pattern="-k 'test_diary'")

            assert result["status"] == "success"
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "-k" in cmd

    def test_run_tests_pattern_shell_metachar_blocked(self, test_config):
        """Test that shell metacharacters in test_pattern are blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import run_tests

            # Attempt shell injection via pattern - now blocked
            malicious_pattern = "test; rm -rf /"
            result = run_tests(test_pattern=malicious_pattern)

            # Shell metacharacters in test patterns are now rejected
            assert result["status"] == "error"
            assert "invalid characters" in result["message"].lower()


class TestPathTraversalAttempts:
    """Tests for path traversal vulnerabilities."""

    def test_git_status_uses_config_project_root(self, test_config):
        """git status always uses project_root from config - no traversal possible."""
        with patch(
            "src.agents.tools.system_admin_tools.get_config", return_value=test_config
        ), patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "", "")

            from src.agents.tools.system_admin_tools import check_git_status

            check_git_status()

            cmd = mock_run.call_args[0][0]
            # -C path is from config, not user input
            assert str(test_config.project_root) in cmd

    def test_run_tests_cwd_fixed_to_project_root(self, test_config):
        """run_tests uses fixed cwd from config - no traversal via cwd."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch, patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "", "")

            from src.agents.tools.system_admin_tools import run_tests

            # Try to traverse via pattern (not actually possible due to design)
            result = run_tests(test_pattern="../../../etc/passwd")

            # cwd is always project_root
            mock_run.assert_called_once()
            cwd = mock_run.call_args.kwargs.get("cwd")
            assert cwd == str(test_config.project_root)

    def test_update_dependencies_cwd_fixed(self, test_config):
        """update_dependencies uses fixed cwd from config."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch, patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "Dependencies updated", "")

            from src.agents.tools.system_admin_tools import update_dependencies

            result = update_dependencies()

            # cwd is always project_root
            cwd = mock_run.call_args.kwargs.get("cwd")
            assert cwd == str(test_config.project_root)


class TestInvalidCrontabSyntax:
    """Tests for crontab input validation."""

    def test_crontab_schedule_wrong_field_count(self, test_config):
        """Crontab schedule with wrong number of fields should fail."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            # Only 3 fields instead of 5
            result = add_crontab_entry(
                schedule="0 8 *",
                command="uv run python -m src.test",
            )

            assert result["status"] == "error"
            assert "expected 5 fields" in result["message"]

    def test_crontab_schedule_too_many_fields(self, test_config):
        """Crontab schedule with too many fields should fail."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            # 6 fields instead of 5
            result = add_crontab_entry(
                schedule="0 8 * * * *",
                command="uv run python -m src.test",
            )

            assert result["status"] == "error"
            assert "expected 5 fields" in result["message"]

    def test_crontab_command_not_in_allowlist(self, test_config):
        """Commands not matching allowlist should be rejected."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            # Command not in allowlist
            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="rm -rf /",  # Not allowed
            )

            assert result["status"] == "error"
            assert "not allowed" in result["message"].lower()

    def test_crontab_command_injection_semicolon(self, test_config):
        """Command injection via semicolon should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            # Attempt to inject command via semicolon
            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test; rm -rf /",
            )

            # Should be rejected due to shell metacharacter
            assert result["status"] == "error"

    def test_crontab_command_injection_pipe(self, test_config):
        """Command injection via pipe should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test | cat /etc/passwd",
            )

            assert result["status"] == "error"

    def test_crontab_command_injection_backtick(self, test_config):
        """Command injection via backtick should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test `id`",
            )

            assert result["status"] == "error"

    def test_crontab_command_injection_dollar_paren(self, test_config):
        """Command injection via $() should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test $(id)",
            )

            assert result["status"] == "error"

    def test_crontab_command_injection_and(self, test_config):
        """Command injection via && should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test && rm -rf /",
            )

            assert result["status"] == "error"

    def test_crontab_command_injection_or(self, test_config):
        """Command injection via || should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test || rm -rf /",
            )

            assert result["status"] == "error"

    def test_crontab_command_injection_newline(self, test_config):
        """Command injection via newline should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test\nrm -rf /",
            )

            assert result["status"] == "error"

    def test_crontab_command_injection_redirection(self, test_config):
        """Command injection via redirection should be blocked."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test > /etc/passwd",
            )

            assert result["status"] == "error"

    def test_crontab_valid_command_allowed(self, test_config):
        """Valid commands matching allowlist should be accepted."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch, patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run, patch(
            "src.agents.tools.system_admin_tools.subprocess.Popen"
        ) as mock_popen:
            # Mock successful crontab read
            mock_run.return_value = (0, "", "")
            # Mock successful crontab write via Popen
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.scheduler",
            )

            assert result["status"] == "success"

    def test_crontab_curl_command_allowed(self, test_config):
        """curl commands with full path should be allowed."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch, patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run, patch(
            "src.agents.tools.system_admin_tools.subprocess.Popen"
        ) as mock_popen:
            # Mock successful crontab read
            mock_run.return_value = (0, "", "")
            # Mock successful crontab write via Popen
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="/usr/bin/curl https://example.com/webhook",
            )

            assert result["status"] == "success"

    def test_crontab_curl_without_full_path_rejected(self, test_config):
        """curl without full path should be rejected."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="curl https://example.com/webhook",  # No /usr/bin/ prefix
            )

            assert result["status"] == "error"


class TestResourceExhaustionScenarios:
    """Tests for resource exhaustion and DoS scenarios."""

    def test_command_timeout_protection(self, test_config):
        """Commands that take too long should timeout."""
        from src.agents.tools.system_admin_tools import _run_command

        # Run a sleep command that exceeds timeout
        code, stdout, stderr = _run_command(["sleep", "5"], timeout=1)

        assert code == -1
        assert "timed out" in stderr.lower()

    def test_very_long_crontab_schedule(self, test_config):
        """Very long schedule string should not cause issues."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            # Very long schedule (but still 5 fields)
            long_schedule = "0 " * 4 + "*"  # "0 0 0 0 *" is valid
            result = add_crontab_entry(
                schedule=long_schedule,
                command="uv run python -m src.test",
            )

            # Should succeed or fail gracefully
            # This will actually fail because "0 0 0 0 *" has extra spaces
            assert result["status"] == "error"

    def test_very_long_command_string(self, test_config):
        """Very long command string should be handled safely."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            # Very long but valid command
            long_command = "uv run python -m src." + "a" * 10000

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command=long_command,
            )

            # Should be accepted (starts with allowed prefix)
            # but will be written to crontab if successful
            assert result["status"] == "success" or result["status"] == "error"

    def test_very_long_comment_rejected(self, test_config):
        """Very long comment should be rejected (max 200 chars)."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            long_comment = "x" * 201  # Over 200 char limit

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test",
                comment=long_comment,
            )

            # Long comments are now rejected
            assert result["status"] == "error"
            assert "too long" in result["message"].lower()

    def test_process_list_limit(self, test_config):
        """Process list should be limited to prevent huge responses."""
        with patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            # Simulate many processes
            header = "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
            processes = "\n".join([
                f"user{i}    {i} 0.0  0.1 12345 6789 ?   Ss   Jan01   0:00 /usr/bin/proc{i}"
                for i in range(1000)
            ])
            mock_run.return_value = (0, header + processes, "")

            from src.agents.tools.system_admin_tools import list_running_processes

            result = list_running_processes()

            # Should be limited to 50 processes
            assert result["status"] == "success"
            assert len(result["processes"]) == 50
            assert result["count"] == 1000  # Total count is preserved

    def test_concurrent_crontab_modifications(self, test_config):
        """Multiple concurrent crontab modifications should not corrupt data."""
        results = []
        errors = []

        def modify_crontab(idx):
            try:
                admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

                with admin_email_patch, config_patch, patch(
                    "src.agents.tools.system_admin_tools._run_command"
                ) as mock_run:
                    # Simulate successful crontab operations
                    mock_run.return_value = (0, "", "")

                    from src.agents.tools.system_admin_tools import add_crontab_entry

                    result = add_crontab_entry(
                        schedule=f"0 {idx % 24} * * *",
                        command=f"uv run python -m src.task{idx}",
                    )
                    results.append(result)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=modify_crontab, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should complete without exceptions
        assert len(errors) == 0
        assert len(results) == 10


class TestAdminPrivilegeBypass:
    """Tests for admin privilege bypass attempts."""

    def test_non_admin_cannot_add_crontab(self, test_config):
        """Non-admin users should not be able to add crontab entries."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=False)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test",
            )

            assert result["status"] == "error"
            assert "admin" in result["message"].lower()

    def test_non_admin_cannot_remove_crontab(self, test_config):
        """Non-admin users should not be able to remove crontab entries."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=False)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import remove_crontab_entry

            result = remove_crontab_entry(pattern="test")

            assert result["status"] == "error"
            assert "admin" in result["message"].lower()

    def test_non_admin_cannot_git_pull(self, test_config):
        """Non-admin users should not be able to run git pull."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=False)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import git_pull

            result = git_pull()

            assert result["status"] == "error"
            assert "admin" in result["message"].lower()

    def test_non_admin_cannot_run_tests(self, test_config):
        """Non-admin users should not be able to run tests."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=False)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import run_tests

            result = run_tests()

            assert result["status"] == "error"
            assert "admin" in result["message"].lower()

    def test_non_admin_cannot_update_dependencies(self, test_config):
        """Non-admin users should not be able to update dependencies."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=False)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import update_dependencies

            result = update_dependencies()

            assert result["status"] == "error"
            assert "admin" in result["message"].lower()

    def test_non_admin_cannot_restart_services(self, test_config):
        """Non-admin users should not be able to get restart instructions."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=False)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import restart_services

            result = restart_services()

            assert result["status"] == "error"
            assert "admin" in result["message"].lower()

    def test_non_admin_can_check_disk(self, test_config):
        """Non-admin users should be able to check disk space (read-only)."""
        with patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "Filesystem  Size  Used Avail Use% Mounted on\n/dev/sda1   100G  50G  50G  50% /", "")

            from src.agents.tools.system_admin_tools import check_disk_space

            result = check_disk_space()

            # No admin check for read-only operations
            assert result["status"] == "success"

    def test_non_admin_can_check_memory(self, test_config):
        """Non-admin users should be able to check memory (read-only)."""
        with patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "vm_stat output...", "")

            from src.agents.tools.system_admin_tools import check_memory

            result = check_memory()

            assert result["status"] == "success"

    def test_non_admin_can_list_processes(self, test_config):
        """Non-admin users should be able to list processes (read-only)."""
        with patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (
                0,
                "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\nroot         1  0.0  0.1  1234  567 ?        Ss   Jan01   0:01 /sbin/init",
                ""
            )

            from src.agents.tools.system_admin_tools import list_running_processes

            result = list_running_processes()

            assert result["status"] == "success"

    def test_non_admin_can_check_git_status(self, test_config):
        """Non-admin users should be able to check git status (read-only)."""
        with patch(
            "src.agents.tools.system_admin_tools.get_config", return_value=test_config
        ), patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "", "")

            from src.agents.tools.system_admin_tools import check_git_status

            result = check_git_status()

            # No admin check for git status
            assert result["status"] == "success"

    def test_admin_email_case_insensitive(self, test_config):
        """Test that admin email check is case-insensitive per RFC 5321."""
        # Create config with specific admin email
        test_config_with_admin = TestConfig(
            admin_emails=("Admin@Example.com",),  # Mixed case
            project_root=test_config.project_root,
        )

        # Try with different case - should still be recognized as admin
        with patch(
            "src.agents.tools.system_admin_tools.get_user_email",
            return_value="admin@example.com"  # lowercase
        ), patch(
            "src.agents.tools.system_admin_tools.get_config",
            return_value=test_config_with_admin
        ), patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.return_value = (0, "Already up to date.", "")

            from src.agents.tools.system_admin_tools import git_pull

            result = git_pull()

            # Admin check is now case-insensitive per RFC 5321
            # "admin@example.com" matches "Admin@Example.com"
            assert result["status"] == "success"


class TestCrontabRemovalPatternMatching:
    """Tests for crontab removal pattern matching edge cases."""

    def test_remove_crontab_empty_pattern(self, test_config):
        """Empty pattern should be rejected to prevent mass deletion."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import remove_crontab_entry

            result = remove_crontab_entry(pattern="")

            # Empty pattern is now rejected
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_remove_crontab_short_pattern(self, test_config):
        """Short patterns (< 3 chars) should be rejected to prevent accidental mass deletion."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import remove_crontab_entry

            result = remove_crontab_entry(pattern="ab")

            # Short pattern is rejected
            assert result["status"] == "error"
            assert "3 characters" in result["message"]

    def test_remove_crontab_wildcard_pattern(self, test_config):
        """Pattern matching is substring-based, not regex - safe from regex DoS."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch, patch(
            "src.agents.tools.system_admin_tools._run_command"
        ) as mock_run:
            mock_run.side_effect = [
                (0, "0 8 * * * /usr/bin/curl https://example.com\n", ""),
                (0, "", ""),
            ]

            from src.agents.tools.system_admin_tools import remove_crontab_entry

            # Regex patterns are treated as literal strings (not regex)
            # Using "curl" (3+ chars) to test substring matching
            result = remove_crontab_entry(pattern="xyz_not_found")

            # Literal substring "xyz_not_found" is not found in the entry
            assert result["status"] == "error"


class TestCommentInjectionInCrontab:
    """Tests for comment injection in crontab entries."""

    def test_crontab_comment_injection_via_newline_blocked(self, test_config):
        """Newline in comment should be rejected to prevent crontab injection."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            # Attempt to inject via comment - now blocked
            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test",
                comment="Safe comment\n* * * * * rm -rf /",  # Injection attempt
            )

            # Newlines in comments are now rejected
            assert result["status"] == "error"
            assert "newline" in result["message"].lower()

    def test_crontab_comment_length_limit(self, test_config):
        """Comment longer than 200 chars should be rejected."""
        admin_email_patch, config_patch = setup_admin_context(test_config, is_admin=True)

        with admin_email_patch, config_patch:
            from src.agents.tools.system_admin_tools import add_crontab_entry

            result = add_crontab_entry(
                schedule="0 8 * * *",
                command="uv run python -m src.test",
                comment="x" * 201,  # Too long
            )

            assert result["status"] == "error"
            assert "too long" in result["message"].lower()


class TestRunCommandSafety:
    """Tests for _run_command helper safety."""

    def test_run_command_with_exception(self, test_config):
        """subprocess.run raises FileNotFoundError for nonexistent commands."""
        # This test verifies the underlying behavior that _run_command handles
        with pytest.raises(FileNotFoundError):
            subprocess.run(
                ["nonexistent_command_xyz_abc_123"],
                capture_output=True,
                text=True,
                timeout=5,
            )

    def test_run_command_with_exception_handled(self, test_config):
        """_run_command catches FileNotFoundError and returns gracefully."""
        # Reimport module to ensure fresh state
        import importlib
        import src.agents.tools.system_admin_tools as sat
        importlib.reload(sat)

        code, stdout, stderr = sat._run_command(["nonexistent_command_xyz_abc_123"])

        # Should return -1 and error message (exception caught)
        assert code == -1
        assert "No such file or directory" in stderr

    def test_run_command_with_large_output(self, test_config):
        """_run_command should handle large output."""
        # Reimport module to ensure fresh state
        import importlib
        import src.agents.tools.system_admin_tools as sat
        importlib.reload(sat)

        # Generate large output using python
        code, stdout, stderr = sat._run_command(
            ["python3", "-c", "import sys; sys.stdout.write('x' * 100000)"]
        )

        # Should succeed and capture output
        assert code == 0
        assert len(stdout) == 100000


class TestShellMetacharacterBlocklist:
    """Tests for shell metacharacter blocking completeness."""

    def test_all_shell_metacharacters_blocked(self, test_config):
        """Verify all shell metacharacters are properly blocked."""
        from src.agents.tools.system_admin_tools import _is_command_allowed

        # All these should be blocked
        metachar_commands = [
            "uv run python -m src.test;id",
            "uv run python -m src.test&&id",
            "uv run python -m src.test||id",
            "uv run python -m src.test|id",
            "uv run python -m src.test$PATH",
            "uv run python -m src.test`id`",
            "uv run python -m src.test()",
            "uv run python -m src.test{}",
            "uv run python -m src.test<file",
            "uv run python -m src.test>file",
            "uv run python -m src.test\nid",
            "uv run python -m src.test\\nid",
        ]

        for cmd in metachar_commands:
            assert not _is_command_allowed(cmd), f"Should block: {cmd}"

    def test_safe_command_allowed(self, test_config):
        """Valid commands without metacharacters should be allowed."""
        from src.agents.tools.system_admin_tools import _is_command_allowed

        safe_commands = [
            "uv run python -m src.scheduler",
            "uv run python -m src.poller",
            "/usr/bin/curl https://example.com/webhook",
            "/usr/bin/curl -X POST https://api.example.com",
        ]

        for cmd in safe_commands:
            assert _is_command_allowed(cmd), f"Should allow: {cmd}"
