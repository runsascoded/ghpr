"""CLI commands for ghpr."""

import re
import sys
import difflib
from functools import partial
from glob import glob
from os import chdir, environ, unlink
from os.path import abspath, dirname, exists, join
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
import webbrowser
import subprocess

from click import Choice, Context, group
from utz import proc, err, cd
from utz.cli import arg, flag, opt

from .api import get_item_metadata, get_pr_metadata, get_current_github_user, get_item_comments
from .comments import write_comment_file, read_comment_file, get_comment_id_from_filename
from .config import get_pr_info_from_path
from .files import (
    get_expected_description_filename,
    find_description_file,
    read_description_from_git,
    write_description_with_link_ref,
    read_description_file,
    upload_image_to_github,
    process_images_in_description,
)
from .gist import (
    create_gist,
    find_gist_remote,
    extract_gist_footer,
    add_gist_footer,
    DEFAULT_GIST_REMOTE,
)
from .patterns import (
    extract_title_from_first_line,
    parse_pr_spec,
    PR_LINK_IN_H1_PATTERN,
    PR_INLINE_LINK_PATTERN,
    PR_LINK_REF_PATTERN,
    PR_SPEC_PATTERN,
    PR_FILENAME_PATTERN,
    PR_DIR_PATTERN,
    GH_DIR_PATTERN,
    GIST_ID_PATTERN,
    GIST_URL_WITH_USER_PATTERN,
)


def render_comment_diff(
    owner: str,
    repo: str,
    number: str,
    item_type: str,
    use_color: bool = True,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Render comment differences between local and remote.

    Returns:
        (drafts_count, changes_count): Number of draft comments and changed comments
    """
    # ANSI color codes
    RED = '\033[31m' if use_color else ''
    GREEN = '\033[32m' if use_color else ''
    CYAN = '\033[36m' if use_color else ''
    YELLOW = '\033[33m' if use_color else ''
    RESET = '\033[0m' if use_color else ''
    BOLD = '\033[1m' if use_color else ''

    # Check for draft comments (new*.md files) from HEAD
    try:
        head_files = proc.lines('git', 'ls-tree', '--name-only', 'HEAD', log=False)
        draft_files = [f for f in head_files if f.startswith('new') and f.endswith('.md')]
    except Exception:
        draft_files = []

    drafts_count = 0
    if draft_files:
        err(f"\n{BOLD}=== Draft comments to post ==={RESET}")
        for draft_file in draft_files:
            try:
                draft_content = proc.text('git', 'show', f'HEAD:{draft_file}', log=False)
                if not draft_content.strip():
                    continue

                drafts_count += 1
                err(f"\n{BOLD}New comment from {draft_file}:{RESET}")
                # Show preview in green (it's being added)
                lines = draft_content.strip().split('\n')
                preview = '\n'.join(lines[:10])
                if len(lines) > 10:
                    err(f"{GREEN}{preview}{RESET}")
                    err(f"{BOLD}... ({len(lines) - 10} more lines){RESET}")
                else:
                    err(f"{GREEN}{preview}{RESET}")
            except Exception as e:
                err(f"Warning: Could not read {draft_file}: {e}")

    # Get remote comments
    remote_comments = get_item_comments(owner, repo, number, item_type)
    remote_comments_by_id = {str(c['id']): c for c in remote_comments}

    # Find all local comment files
    comment_files = sorted(glob('z*.md'))

    changes_count = 0
    if comment_files:
        local_comment_ids = set()
        for comment_file_path in comment_files:
            comment_id = get_comment_id_from_filename(comment_file_path)
            if not comment_id:
                continue
            local_comment_ids.add(comment_id)

            author, created_at, updated_at, local_body = read_comment_file(Path(comment_file_path))

            if comment_id in remote_comments_by_id:
                # Compare with remote
                remote_comment = remote_comments_by_id[comment_id]
                remote_body = remote_comment.get('body', '').replace('\r\n', '\n')
                comment_url = remote_comment.get('html_url', f'Comment {comment_id}')

                if local_body != remote_body:
                    changes_count += 1
                    err(f"\n{BOLD}{YELLOW}Comment {comment_id} (by {author}) - Differences:{RESET}")
                    render_unified_diff(
                        remote_body,
                        local_body,
                        fromfile=comment_url,
                        tofile=comment_file_path,
                        use_color=use_color,
                        log=print
                    )
                else:
                    err(f"{CYAN}Comment {comment_id} (by {author}): No differences{RESET}")
            else:
                err(f"{YELLOW}Comment {comment_id} exists locally but not remotely{RESET}")

        # Check for remote comments not present locally
        for remote_comment in remote_comments:
            comment_id = str(remote_comment['id'])
            if comment_id not in local_comment_ids:
                author = remote_comment.get('user', {}).get('login', 'unknown')
                err(f"{YELLOW}Comment {comment_id} (by {author}) exists remotely but not locally{RESET}")

    return drafts_count, changes_count


def render_unified_diff(
    remote_content: str,
    local_content: str,
    fromfile: str,
    tofile: str,
    use_color: bool = True,
    log=None,
) -> None:
    """Render a colored unified diff.

    Args:
        remote_content: Remote content to compare
        local_content: Local content to compare
        fromfile: Label for remote content
        tofile: Label for local content
        use_color: Whether to use ANSI color codes
        log: Function to use for output (default: err for stderr)
    """
    if log is None:
        log = err

    # ANSI color codes
    RED = '\033[31m' if use_color else ''
    GREEN = '\033[32m' if use_color else ''
    CYAN = '\033[36m' if use_color else ''
    BOLD = '\033[1m' if use_color else ''
    RESET = '\033[0m' if use_color else ''

    # Check if contents have final newlines
    remote_has_final_newline = remote_content.endswith('\n')
    local_has_final_newline = local_content.endswith('\n')

    # For proper diff display, normalize both to end with newline for comparison
    # This prevents difflib from showing the last line as changed when only the
    # trailing newline differs
    remote_normalized = remote_content if remote_has_final_newline else remote_content + '\n'
    local_normalized = local_content if local_has_final_newline else local_content + '\n'

    local_lines = local_normalized.splitlines(keepends=True)
    remote_lines = remote_normalized.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        remote_lines,
        local_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm=''
    ))

    # Only show diff if there are actual content differences
    if diff_lines:
        for line in diff_lines:
            line = line.rstrip('\n')
            if line.startswith('+++'):
                log(f"{BOLD}{line}{RESET}")
            elif line.startswith('---'):
                log(f"{BOLD}{line}{RESET}")
            elif line.startswith('@@'):
                log(f"{CYAN}{line}{RESET}")
            elif line.startswith('+'):
                log(f"{GREEN}{line}{RESET}")
            elif line.startswith('-'):
                log(f"{RED}{line}{RESET}")
            else:
                log(line)

        # Add git-style "No newline at end of file" indicator after the diff
        if not remote_has_final_newline:
            log(f"{CYAN}\\ No newline at end of file{RESET}")
        if remote_has_final_newline and not local_has_final_newline:
            log(f"{CYAN}\\ No newline at end of file{RESET}")
    elif remote_has_final_newline != local_has_final_newline:
        # Only difference is trailing newline - show minimal diff
        log(f"{BOLD}--- {fromfile}{RESET}")
        log(f"{BOLD}+++ {tofile}{RESET}")
        log(f"{CYAN}Only trailing newline differs{RESET}")


# Try to import git_helpers, but it's OK if not available
try:
    from git_helpers.util.branch_resolution import resolve_remote_ref
except ImportError:
    # Fallback: define a stub that raises an informative error
    def resolve_remote_ref(verbose=False):
        raise ImportError(
            "git_helpers not available. Install it or specify --head explicitly."
        )


def get_owner_repo(repo_arg: str | None = None) -> tuple[str, str]:
    """Get owner and repo, trying multiple sources.

    Tries in order:
    1. Explicit -r/--repo argument (owner/repo format)
    2. Git config (pr.owner, pr.repo)
    3. Parent directory's GitHub repo
    4. Current directory's git remotes (origin, then any)

    Returns:
        Tuple of (owner, repo)

    Raises:
        SystemExit if unable to determine repo
    """
    # Try explicit argument
    if repo_arg:
        if '/' in repo_arg:
            parts = repo_arg.split('/')
            if len(parts) == 2:
                return parts[0], parts[1]
        err(f"Error: Invalid repo format '{repo_arg}'. Use: owner/repo")
        exit(1)

    # Try git config
    owner = proc.line('git', 'config', 'pr.owner', err_ok=True, log=None)
    repo = proc.line('git', 'config', 'pr.repo', err_ok=True, log=None)
    if owner and repo:
        return owner, repo

    # Try walking up to find a git repo with GitHub remote
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / '.git').exists():
            try:
                with cd(parent):
                    repo_data = proc.json('gh', 'repo', 'view', '--json', 'owner,name', log=None, err_ok=True)
                    if repo_data:
                        return repo_data['owner']['login'], repo_data['name']
            except Exception:
                pass
            # Continue searching even if gh failed - might find a parent with GitHub remote

    # Try current directory's git remotes
    try:
        remotes = proc.lines('git', 'remote', log=None, err_ok=True)
        if remotes:
            # Try 'origin' first
            remote_to_try = 'origin' if 'origin' in remotes else remotes[0]
            remote_url = proc.line('git', 'remote', 'get-url', remote_to_try, log=None, err_ok=True)
            if remote_url:
                from ghpr.patterns import GITHUB_URL_PATTERN
                match = GITHUB_URL_PATTERN.search(remote_url)
                if match:
                    return match.group(1), match.group(2)
    except Exception:
        pass

    err("Error: Could not determine repository.")
    err("Specify with: -r owner/repo")
    err("Or configure with: ghpr init -r owner/repo")
    err("Or run from a directory with a GitHub remote")
    exit(1)


@group()
def cli():
    """Clone and sync GitHub PR descriptions."""
    pass




# Register modular commands
from .commands import shell_integration as shell_integration_cmd
from .commands import show as show_cmd
from .commands import open as open_cmd
from .commands import upload as upload_cmd
from .commands import diff as diff_cmd
from .commands import pull as pull_cmd
from .commands import clone as clone_cmd
from .commands import create as create_cmd
from .commands import push as push_cmd
from .commands import ingest_attachments as ingest_attachments_cmd

shell_integration_cmd.register(cli)
show_cmd.register(cli)
open_cmd.register(cli)
upload_cmd.register(cli)
diff_cmd.register(cli)
pull_cmd.register(cli)
clone_cmd.register(cli)
create_cmd.register(cli)
push_cmd.register(cli)
ingest_attachments_cmd.register(cli)


if __name__ == '__main__':
    cli()
