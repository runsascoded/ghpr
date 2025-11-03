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




@cli.command()
@opt('-r', '--repo', help='Repository (owner/repo format)')
@opt('-b', '--base', help='Base branch (default: repo default branch)')
def init(
    repo: str | None,
    base: str | None,
) -> None:
    """Initialize a new PR draft in the current directory."""
    # Check if we're already in a PR directory
    if exists('DESCRIPTION.md'):
        err("Error: DESCRIPTION.md already exists. Are you already managing a PR here?")
        exit(1)

    # Get and store repo config BEFORE creating .git
    if repo:
        # Explicit repo provided
        owner, repo_name = repo.split('/')
    else:
        # Try to auto-detect from parent directory's git repo
        owner = None
        repo_name = None
        parent = Path('..').resolve()

        # Walk up to find a git repo
        for check_dir in [parent] + list(parent.parents):
            if (check_dir / '.git').exists():
                try:
                    with cd(check_dir):
                        repo_data = proc.json('gh', 'repo', 'view', '--json', 'owner,name', log=None, err_ok=True)
                        if repo_data:
                            owner = repo_data['owner']['login']
                            repo_name = repo_data['name']
                            err(f"Auto-detected repository: {owner}/{repo_name}")
                            break
                except Exception:
                    pass

    # Initialize git repo if needed
    if not exists('.git'):
        proc.run('git', 'init', '-q', log=None)
        err("Initialized git repository")

    if owner and repo_name:
        proc.run('git', 'config', 'pr.owner', owner, log=None)
        proc.run('git', 'config', 'pr.repo', repo_name, log=None)
        if repo:
            err(f"Configured for {owner}/{repo_name}")

    if base:
        proc.run('git', 'config', 'pr.base', base, log=None)
        err(f"Base branch: {base}")

    # Create initial DESCRIPTION.md
    with open('DESCRIPTION.md', 'w') as f:
        if repo:
            f.write(f"# {repo}#NUMBER Title\n\n")
        else:
            f.write("# owner/repo#NUMBER Title\n\n")
        f.write("Description of the PR...\n")

    err("Created DESCRIPTION.md template")
    err("Edit the file with your PR title and description, then commit")
    err("Use 'ghpr create' to create the PR when ready")


def _read_and_parse_description() -> tuple[str, str]:
    """Read DESCRIPTION.md and parse title and body.

    Returns:
        (title, body) tuple
    """
    if not exists('DESCRIPTION.md'):
        err("Error: DESCRIPTION.md not found. Run 'ghpr init' first")
        exit(1)

    with open('DESCRIPTION.md', 'r') as f:
        content = f.read()

    lines = content.split('\n')
    if not lines:
        err("Error: DESCRIPTION.md is empty")
        exit(1)

    # Parse title from first line
    first_line = lines[0].strip()
    if first_line.startswith('#'):
        title = first_line.lstrip('#').strip()
        # Remove any [owner/repo#NUM] prefix if present
        title = re.sub(r'^\[?[^/\]]+/[^#\]]+#\d+]?\s*', '', title)
        title = re.sub(r'^[^/]+/[^#]+#\w+\s+', '', title)  # Handle owner/repo#NUMBER format
    else:
        title = first_line

    # Get body (rest of the file)
    body_lines = lines[1:]
    while body_lines and not body_lines[0].strip():
        body_lines = body_lines[1:]
    body = '\n'.join(body_lines).strip()

    return title, body


def _finalize_created_item(
    owner: str,
    repo: str,
    number: str,
    url: str,
    item_type: str,
) -> None:
    """Finalize after creating PR/issue: rename file, commit, rename directory.

    Args:
        owner: Repository owner
        repo: Repository name
        number: PR/issue number
        url: GitHub URL
        item_type: 'pr' or 'issue'
    """
    old_file = Path('DESCRIPTION.md')
    new_filename = f'{repo}#{number}.md'
    new_file = Path(new_filename)

    # Read title and body from DESCRIPTION.md
    title, body = read_description_file()
    if not title:
        err("Warning: Could not parse title from DESCRIPTION.md")
        return

    # Write using helper with proper link reference format
    write_description_with_link_ref(
        new_file,
        owner,
        repo,
        number,
        title,
        body or '',
        url
    )

    # Remove old file if different name
    if old_file != new_file:
        old_file.unlink()
        err(f"Renamed DESCRIPTION.md to {new_filename}")

    # Git operations
    proc.run('git', 'add', new_filename, log=None)
    if old_file != new_file:
        proc.run('git', 'rm', 'DESCRIPTION.md', log=None)
    item_label = 'PR' if item_type == 'pr' else 'issue'
    proc.run('git', 'commit', '-m', f'Rename to {new_filename} and add {item_label} #{number} link', log=None)
    err(f"Updated {new_filename} with {item_label} link")

    # Rename directory from gh/new to gh/{number}
    current_dir = Path.cwd()
    parent_dir = current_dir.parent
    current_name = current_dir.name

    # Check if we're in a gh/* subdirectory
    if parent_dir.name == 'gh' and current_name != number:
        new_dir = parent_dir / number
        if not new_dir.exists():
            # Note: After this, our cwd will be invalid, but we're done anyway
            import os
            os.rename(str(current_dir), str(new_dir))
            err(f"Renamed directory: gh/{current_name} → gh/{number}")
        else:
            err(f"Warning: Directory gh/{number} already exists, not renaming")


@cli.command()
@opt('-b', '--base', help='Base branch (default: repo default branch)')
@flag('-d', '--draft', help='Create as draft PR')
@opt('-h', '--head', help='Head branch (default: auto-detect from parent repo)')
@flag('-i', '--issue', help='Create an issue instead of a PR')
@flag('-n', '--dry-run', help='Show what would be done without creating')
@opt('-r', '--repo', help='Repository (owner/repo format, default: auto-detect)')
@flag('-w', '--web', help='Open in web browser after creating')
def create(
    head: str | None,
    base: str | None,
    draft: bool,
    issue: bool,
    repo: str | None,
    web: bool,
    dry_run: bool,
) -> None:
    """Create a new PR or Issue from the current draft."""
    if issue:
        create_new_issue(repo, web, dry_run)
    else:
        create_new_pr(head, base, draft, repo, web, dry_run)


def create_new_pr(
    head: str | None,
    base: str | None,
    draft: bool,
    repo_arg: str | None,
    web: bool,
    dry_run: bool,
) -> None:
    """Create a new PR from DESCRIPTION.md."""
    # Read and parse DESCRIPTION.md
    title, body = _read_and_parse_description()

    # Get repo info from config or parent directory
    owner = proc.line('git', 'config', 'pr.owner', err_ok=True, log=None)
    repo = proc.line('git', 'config', 'pr.repo', err_ok=True, log=None)

    if not owner or not repo:
        # Try to get from parent directory
        parent_dir = Path('..').resolve()
        if exists(join(parent_dir, '.git')):
            try:
                with cd(parent_dir):
                    repo_data = proc.json('gh', 'repo', 'view', '--json', 'owner,name', log=None)
                    owner = repo_data['owner']['login']
                    repo = repo_data['name']
            except Exception as e:
                err(f"Error: Could not determine repository: {e}")
                err("Configure with 'ghpr init -r owner/repo'")
                exit(1)
        else:
            err("Error: Could not determine repository. Configure with 'ghpr init -r owner/repo'")
            exit(1)

    # Get base branch from config or default
    if not base:
        base = proc.line('git', 'config', 'pr.base', err_ok=True, log=None)
        if not base:
            # Try to get default branch from parent repo
            try:
                parent_dir = Path('..').resolve()
                if exists(join(parent_dir, '.git')):
                    with cd(parent_dir):
                        # Get default branch from GitHub
                        default_branch = proc.line('gh', 'repo', 'view', '--json', 'defaultBranchRef', '-q', '.defaultBranchRef.name', log=None)
                        base = default_branch
                    err(f"Auto-detected base branch: {base}")
                else:
                    base = 'main'  # Fallback to main
            except Exception as e:
                err(f"Error: Could not detect base branch: {e}")
                raise

    # Get head branch - try to auto-detect from parent repo
    if not head:
        parent_dir = Path('..').resolve()
        if exists(join(parent_dir, '.git')):
            try:
                with cd(parent_dir):
                    # Use branch resolution
                    ref_name, remote_ref = resolve_remote_ref(verbose=False)
                    if ref_name:
                        head = ref_name
                        err(f"Auto-detected head branch: {head}")

                    if not head:
                        # Fallback to current branch
                        head = proc.line('git', 'rev-parse', '--abbrev-ref', 'HEAD', log=None)
                        if head == 'HEAD':
                            err("Error: Parent repo is in detached HEAD state. Specify --head explicitly")
                            exit(1)
            except Exception as e:
                err(f"Error detecting head branch: {e}")
                err("Specify --head explicitly")
                exit(1)
        else:
            err("Error: Could not detect head branch. Specify --head explicitly")
            exit(1)

    # Create the PR
    if dry_run:
        err(f"[DRY-RUN] Would create PR in {owner}/{repo}")
        err(f"  Title: {title}")
        err(f"  Base: {base}")
        err(f"  Head: {head}")
        if draft:
            err("  Type: Draft PR")
        if body:
            err(f"  Body ({len(body)} chars):")
            # Show first few lines of body
            body_preview = body[:500] + ('...' if len(body) > 500 else '')
            for line in body_preview.split('\n')[:10]:
                err(f"    {line}")
    else:
        cmd = ['gh', 'pr', 'create',
               '-R', f'{owner}/{repo}',
               '--title', title,
               '--body', body,
               '--base', base,
               '--head', head]

        if draft:
            cmd.append('--draft')

        if web:
            cmd.append('--web')

        try:
            output = proc.text(*cmd, log=None).strip()
            if not web:
                # Extract PR number from URL
                match = re.search(r'/pull/(\d+)', output)
                if match:
                    pr_number = match.group(1)
                    # Store PR info in git config
                    proc.run('git', 'config', 'pr.number', pr_number, log=None)
                    proc.run('git', 'config', 'pr.url', output, log=None)
                    err(f"Created PR #{pr_number}: {output}")
                    err("PR info stored in git config")

                    # Check for gist remote and store its ID if found
                    try:
                        remotes = proc.lines('git', 'remote', '-v', log=None)
                        for remote_line in remotes:
                            if 'gist.github.com' in remote_line:
                                # Extract gist ID from URL like git@gist.github.com:GIST_ID.git
                                gist_match = GIST_ID_PATTERN.search(remote_line)
                                if gist_match:
                                    gist_id = gist_match.group(1)
                                    proc.run('git', 'config', 'pr.gist', gist_id, log=None)
                                    err(f"Detected and stored gist ID: {gist_id}")
                                    break
                    except Exception:
                        # Gist detection is optional, silently continue
                        pass

                    # Finalize: rename file, commit, rename directory
                    _finalize_created_item(owner, repo, pr_number, output, 'pr')
                else:
                    err(f"Created PR: {output}")
        except Exception as e:
            err(f"Error creating PR: {e}")
            exit(1)


def create_new_issue(
    repo_arg: str | None,
    web: bool,
    dry_run: bool,
) -> None:
    """Create a new Issue from DESCRIPTION.md."""
    # Read and parse DESCRIPTION.md
    title, body = _read_and_parse_description()

    # Get repo info
    owner, repo = get_owner_repo(repo_arg)

    # Create the issue
    if dry_run:
        err(f"[DRY-RUN] Would create issue in {owner}/{repo}")
        err(f"  Title: {title}")
        if body:
            err(f"  Body ({len(body)} chars):")
            # Show first few lines of body
            body_preview = body[:500] + ('...' if len(body) > 500 else '')
            for line in body_preview.split('\n')[:10]:
                err(f"    {line}")
    else:
        cmd = ['gh', 'issue', 'create',
               '-R', f'{owner}/{repo}',
               '--title', title,
               '--body', body]

        if web:
            cmd.append('--web')

        try:
            output = proc.text(*cmd, log=None).strip()
            if not web:
                # Extract issue number from URL
                match = re.search(r'/issues/(\d+)', output)
                if match:
                    issue_number = match.group(1)
                    # Store issue info in git config
                    proc.run('git', 'config', 'pr.number', issue_number, log=None)
                    proc.run('git', 'config', 'pr.type', 'issue', log=None)
                    proc.run('git', 'config', 'pr.url', output, log=None)
                    err(f"Created issue #{issue_number}: {output}")
                    err("Issue info stored in git config")

                    # Finalize: rename file, commit, rename directory
                    _finalize_created_item(owner, repo, issue_number, output, 'issue')
            else:
                err(f"Created issue: {output}")
        except Exception as e:
            err(f"Error creating issue: {e}")
            exit(1)



# Register modular commands
from .commands import shell_integration as shell_integration_cmd
from .commands import show as show_cmd
from .commands import open as open_cmd
from .commands import upload as upload_cmd
from .commands import diff as diff_cmd
from .commands import pull as pull_cmd
from .commands import clone as clone_cmd
from .commands import push as push_cmd
from .commands import ingest_attachments as ingest_attachments_cmd

shell_integration_cmd.register(cli)
show_cmd.register(cli)
open_cmd.register(cli)
upload_cmd.register(cli)
diff_cmd.register(cli)
pull_cmd.register(cli)
clone_cmd.register(cli)
push_cmd.register(cli)
ingest_attachments_cmd.register(cli)


if __name__ == '__main__':
    cli()
