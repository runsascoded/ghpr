"""Tests for create command with mocked gh API calls."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from tempfile import TemporaryDirectory
import os
from click.testing import CliRunner

from ghpr.cli import cli
from ghpr.commands.create import create_new_pr, create_new_issue


class TestInit:
    """Test init command."""

    def test_init_with_explicit_repo(self, tmp_path):
        """Test init with -r owner/repo flag."""
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            with patch('ghpr.commands.create.proc') as mock_proc:
                result = runner.invoke(cli, ['init', '-r', 'test-owner/test-repo'])

                assert result.exit_code == 0

                # Check git init was called
                assert any('git' in str(call) and 'init' in str(call) for call in mock_proc.run.call_args_list)

                # Check git config calls
                config_calls = [str(call) for call in mock_proc.run.call_args_list if 'config' in str(call)]
                assert any('pr.owner' in call and 'test-owner' in call for call in config_calls)
                assert any('pr.repo' in call and 'test-repo' in call for call in config_calls)

                # Check DESCRIPTION.md was created
                assert Path('DESCRIPTION.md').exists()

    def test_init_already_initialized(self, tmp_path):
        """Test init fails when DESCRIPTION.md exists."""
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('DESCRIPTION.md').write_text('# Test\n')

            result = runner.invoke(cli, ['init'])
            assert result.exit_code != 0


class TestCreateIssue:
    """Test issue creation with mocked gh calls."""

    def test_create_issue_dry_run(self, tmp_path):
        """Test issue creation in dry-run mode."""
        os.chdir(tmp_path)
        Path('DESCRIPTION.md').write_text('# Test Issue\n\nTest body content\n')
        Path('.git').mkdir()

        with patch('ghpr.commands.create.proc') as mock_proc, \
             patch('ghpr.commands.create.get_owner_repo') as mock_get_repo, \
             patch('ghpr.commands.create.err'):

            mock_get_repo.return_value = ('test-owner', 'test-repo')

            # Should not make any gh calls in dry-run mode
            create_new_issue(repo_arg=None, web=False, dry_run=True)

            # Verify no gh issue create call was made
            gh_calls = [call for call in mock_proc.text.call_args_list if 'gh' in str(call)]
            assert len(gh_calls) == 0

    def test_create_issue_success(self, tmp_path):
        """Test successful issue creation."""
        os.chdir(tmp_path)
        Path('DESCRIPTION.md').write_text('# Test Issue\n\nTest body content\n')
        Path('.git').mkdir()

        with patch('ghpr.commands.create.proc') as mock_proc, \
             patch('ghpr.commands.create.get_owner_repo') as mock_get_repo, \
             patch('ghpr.commands.create.read_description_file') as mock_read_desc, \
             patch('ghpr.commands.create.write_description_with_link_ref') as mock_write, \
             patch('ghpr.commands.create.err'), \
             patch('os.rename'):

            mock_get_repo.return_value = ('test-owner', 'test-repo')
            mock_proc.text.return_value = 'https://github.com/test-owner/test-repo/issues/42'
            mock_read_desc.return_value = ('Test Issue', 'Test body content')

            create_new_issue(repo_arg=None, web=False, dry_run=False)

            # Verify gh issue create was called
            mock_proc.text.assert_called_once()
            call_args = mock_proc.text.call_args[0]
            assert 'gh' in call_args
            assert 'issue' in call_args
            assert 'create' in call_args
            assert '--title' in call_args
            assert 'Test Issue' in call_args

            # Verify git config was set
            config_calls = [call[0] for call in mock_proc.run.call_args_list if 'config' in call[0]]
            assert any('pr.number' in call and '42' in call for call in config_calls)
            assert any('pr.type' in call and 'issue' in call for call in config_calls)

            # Verify file was written with link reference
            mock_write.assert_called_once()
            write_args = mock_write.call_args[0]
            assert write_args[1] == 'test-owner'
            assert write_args[2] == 'test-repo'
            assert write_args[3] == '42'

    def test_create_issue_with_explicit_repo(self, tmp_path):
        """Test issue creation with -r flag."""
        os.chdir(tmp_path)
        Path('DESCRIPTION.md').write_text('# Test Issue\n\nTest body\n')
        Path('.git').mkdir()

        with patch('ghpr.commands.create.proc') as mock_proc, \
             patch('ghpr.commands.create.get_owner_repo') as mock_get_repo, \
             patch('ghpr.commands.create.read_description_file') as mock_read_desc, \
             patch('ghpr.commands.create.write_description_with_link_ref'), \
             patch('ghpr.commands.create.err'), \
             patch('os.rename'):

            mock_get_repo.return_value = ('other-owner', 'other-repo')
            mock_proc.text.return_value = 'https://github.com/other-owner/other-repo/issues/123'
            mock_read_desc.return_value = ('Test Issue', 'Test body')

            create_new_issue(repo_arg='other-owner/other-repo', web=False, dry_run=False)

            # Verify get_owner_repo was called with the arg
            mock_get_repo.assert_called_once_with('other-owner/other-repo')


class TestCreatePR:
    """Test PR creation with mocked gh calls.

    Note: PR creation has complex branch detection logic that makes
    comprehensive mocking difficult. These tests focus on the core
    gh API call behavior. Full integration testing is done manually
    or with real repos.
    """

    def test_create_pr_with_explicit_args(self, tmp_path):
        """Test PR creation with explicit head/base arguments."""
        os.chdir(tmp_path)
        Path('DESCRIPTION.md').write_text('# Test PR\n\nTest body\n')
        Path('.git').mkdir()

        with patch('ghpr.commands.create.proc') as mock_proc, \
             patch('ghpr.commands.create.read_description_file') as mock_read_desc, \
             patch('ghpr.commands.create.write_description_with_link_ref') as mock_write, \
             patch('ghpr.commands.create.err'), \
             patch('os.rename'):

            # Setup mocks for successful flow
            def line_side_effect(*args, **kwargs):
                if 'pr.owner' in args:
                    return 'test-owner'
                elif 'pr.repo' in args:
                    return 'test-repo'
                return ''

            mock_proc.line.side_effect = line_side_effect
            mock_proc.text.return_value = 'https://github.com/test-owner/test-repo/pull/42'
            mock_proc.lines.return_value = []
            mock_read_desc.return_value = ('Test PR', 'Test body')

            # Provide explicit head and base to avoid branch detection
            create_new_pr(
                head='feature-branch',
                base='main',
                draft=False,
                repo_arg=None,
                web=False,
                dry_run=False
            )

            # Verify gh pr create was called with correct args
            mock_proc.text.assert_called_once()
            call_args = mock_proc.text.call_args[0]
            assert 'gh' in call_args
            assert 'pr' in call_args
            assert 'create' in call_args
            assert '--head' in call_args
            assert 'feature-branch' in call_args
            assert '--base' in call_args
            assert 'main' in call_args

    def test_create_draft_pr(self, tmp_path):
        """Test draft PR includes --draft flag."""
        os.chdir(tmp_path)
        Path('DESCRIPTION.md').write_text('# Draft PR\n\nDraft body\n')
        Path('.git').mkdir()

        with patch('ghpr.commands.create.proc') as mock_proc, \
             patch('ghpr.commands.create.read_description_file') as mock_read_desc, \
             patch('ghpr.commands.create.write_description_with_link_ref'), \
             patch('ghpr.commands.create.err'), \
             patch('os.rename'):

            def line_side_effect(*args, **kwargs):
                if 'pr.owner' in args:
                    return 'test-owner'
                elif 'pr.repo' in args:
                    return 'test-repo'
                return ''

            mock_proc.line.side_effect = line_side_effect
            mock_proc.text.return_value = 'https://github.com/test-owner/test-repo/pull/99'
            mock_proc.lines.return_value = []
            mock_read_desc.return_value = ('Draft PR', 'Draft body')

            create_new_pr(
                head='feature',
                base='main',
                draft=True,  # Draft flag
                repo_arg=None,
                web=False,
                dry_run=False
            )

            # Verify --draft flag was passed
            call_args = mock_proc.text.call_args[0]
            assert '--draft' in call_args
