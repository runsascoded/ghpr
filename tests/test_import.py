"""Basic smoke tests to ensure the package is importable and functional."""

import subprocess
import sys


def test_package_imports():
    """Test that all modules can be imported."""
    from ghpr import api, cli, comments, config, files, gist, patterns
    assert api is not None
    assert cli is not None
    assert comments is not None
    assert config is not None
    assert files is not None
    assert gist is not None
    assert patterns is not None


def test_cli_loads():
    """Test that the CLI entry point loads."""
    result = subprocess.run(
        ["ghpr", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Clone and sync GitHub PR descriptions" in result.stdout


def test_all_commands_present():
    """Test that all expected commands are present."""
    result = subprocess.run(
        ["ghpr", "--help"],
        capture_output=True,
        text=True,
    )

    expected_commands = [
        "clone",
        "comment",
        "create",
        "diff",
        "init",
        "ingest-attachments",
        "open",
        "pull",
        "push",
        "shell-integration",
        "show",
        "upload",
    ]

    for cmd in expected_commands:
        assert cmd in result.stdout, f"Command '{cmd}' not found in CLI help"


def test_shell_integration_outputs():
    """Test that shell-integration command produces output."""
    result = subprocess.run(
        ["ghpr", "shell-integration", "bash"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "alias ghpri=" in result.stdout
    assert "alias ghprc=" in result.stdout


def test_patterns_regex():
    """Test that regex patterns compile and work."""
    from ghpr.patterns import parse_pr_spec, extract_title_from_first_line

    # Test PR spec parsing
    owner, repo, number, item_type = parse_pr_spec("owner/repo#123")
    assert owner == "owner"
    assert repo == "repo"
    assert number == "123"

    # Test title extraction
    title = extract_title_from_first_line("# [owner/repo#123] My PR Title")
    assert title == "My PR Title"


def test_comment_filename_parsing():
    """Test comment filename parsing (both old and new formats)."""
    from ghpr.comments import get_comment_id_from_filename

    # New format: z{id}-{author}.md
    comment_id = get_comment_id_from_filename("z123456789-ryan-williams.md")
    assert comment_id == "123456789"

    # Legacy format: z{id}.md
    comment_id = get_comment_id_from_filename("z987654321.md")
    assert comment_id == "987654321"

    # Invalid format
    comment_id = get_comment_id_from_filename("invalid.md")
    assert comment_id is None
