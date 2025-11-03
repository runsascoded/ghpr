"""Create and Init commands - initialize and create PR/Issue."""

import re
from os.path import exists, join
from pathlib import Path
from utz import proc, err, cd
from utz.cli import opt, flag

from ..files import read_description_file, write_description_with_link_ref
from ..patterns import GIST_ID_PATTERN

# Import resolve_remote_ref from utz
try:
    from utz.git.branch import resolve_remote_ref
except ImportError:
    # Fallback: define a stub that raises an informative error
    def resolve_remote_ref(verbose=False):
        raise ImportError(
            "utz.git.branch.resolve_remote_ref not available. Update utz or specify --head explicitly."
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
        SystemExit: If repository cannot be determined
    """
    # 1. Try explicit argument
    if repo_arg:
        try:
            owner, repo = repo_arg.split('/')
            return owner, repo
        except ValueError:
            err(f"Error: Invalid repo format '{repo_arg}'. Use owner/repo format.")
            exit(1)

    # 2. Try git config
    owner = proc.line('git', 'config', 'pr.owner', err_ok=True, log=None)
    repo = proc.line('git', 'config', 'pr.repo', err_ok=True, log=None)
    if owner and repo:
        return owner, repo

    # 3. Try parent directory
    parent_dir = Path('..').resolve()
    if exists(join(parent_dir, '.git')):
        try:
            with cd(parent_dir):
                repo_data = proc.json('gh', 'repo', 'view', '--json', 'owner,name', log=None)
                owner = repo_data['owner']['login']
                repo = repo_data['name']
                return owner, repo
        except Exception:
            pass

    # 4. Try current directory's git remotes
    try:
        remotes = proc.lines('git', 'remote', log=None)
        # Try origin first
        if 'origin' in remotes:
            url = proc.line('git', 'remote', 'get-url', 'origin', log=None)
            owner, repo = _parse_github_url(url)
            if owner and repo:
                return owner, repo

        # Try any remote
        for remote in remotes:
            url = proc.line('git', 'remote', 'get-url', remote, log=None)
            owner, repo = _parse_github_url(url)
            if owner and repo:
                return owner, repo
    except Exception:
        pass

    err("Error: Could not determine repository. Configure with 'ghpr init -r owner/repo' or use -r/--repo")
    exit(1)


def _parse_github_url(url: str) -> tuple[str | None, str | None]:
    """Parse owner and repo from a GitHub URL."""
    import re
    # Match git@github.com:owner/repo.git or https://github.com/owner/repo
    match = re.search(r'github\.com[:/]([^/]+)/([^/\.]+)', url)
    if match:
        return match.group(1), match.group(2)
    return None, None


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


def register(cli):
    """Register commands with CLI."""
    # Register init command
    cli.command()(
        opt('-r', '--repo', help='Repository (owner/repo format)')(
            opt('-b', '--base', help='Base branch (default: repo default branch)')(
                init
            )
        )
    )

    # Register create command
    cli.command()(
        opt('-b', '--base', help='Base branch (default: repo default branch)')(
            flag('-d', '--draft', help='Create as draft PR')(
                opt('-h', '--head', help='Head branch (default: auto-detect from parent repo)')(
                    flag('-i', '--issue', help='Create an issue instead of a PR')(
                        flag('-n', '--dry-run', help='Show what would be done without creating')(
                            opt('-r', '--repo', help='Repository (owner/repo format, default: auto-detect)')(
                                flag('-w', '--web', help='Open in web browser after creating')(
                                    create
                                )
                            )
                        )
                    )
                )
            )
        )
    )
