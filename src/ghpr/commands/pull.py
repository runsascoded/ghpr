"""Pull command - pull latest from GitHub PR/Issue."""

from glob import glob
from pathlib import Path
from utz import proc, err
from utz.cli import flag, opt

from ..api import get_pr_metadata, get_item_metadata, get_item_comments
from ..comments import write_comment_file, read_comment_file, get_comment_id_from_filename
from ..config import get_pr_info_from_path
from ..files import write_description_with_link_ref
from ..gist import extract_gist_footer


def pull(
    gist: bool,
    dry_run: bool,
    footer: bool | None,
    open_browser: bool,
    gist_private: bool | None,
    no_comments: bool,
) -> None:
    """Pull latest description and comments from GitHub PR/Issue."""
    # Import push here to avoid circular dependency
    from . import push as push_module

    # First pull
    err("Pulling latest from GitHub...")

    # Get PR/Issue info
    owner, repo, pr_number = get_pr_info_from_path()

    if not all([owner, repo, pr_number]):
        owner = proc.line('git', 'config', 'pr.owner', err_ok=True, log=None) or ''
        repo = proc.line('git', 'config', 'pr.repo', err_ok=True, log=None) or ''
        pr_number = proc.line('git', 'config', 'pr.number', err_ok=True, log=None) or ''

        if not all([owner, repo, pr_number]):
            err("Error: Could not determine PR/Issue")
            exit(1)

    # Get latest PR/Issue data
    item_data, item_type = get_item_metadata(owner, repo, pr_number)
    if not item_data:
        exit(1)

    # Update local file
    from ..files import get_expected_description_filename
    desc_filename = get_expected_description_filename(owner, repo, pr_number)
    desc_file = Path(desc_filename)
    title = item_data['title']
    body = item_data['body'] or ''
    url = item_data['url']

    # Strip any gist footer from the body before saving locally
    body_without_footer, _ = extract_gist_footer(body)

    # Write using helper to avoid duplicate link definitions
    write_description_with_link_ref(desc_file, owner, repo, pr_number, title, body_without_footer, url)

    # Check if there are changes to description
    item_label = 'issue' if item_type == 'issue' else 'PR'
    desc_changed = not proc.check('git', 'diff', '--exit-code', desc_filename, log=None)
    if desc_changed:
        proc.run('git', 'add', desc_filename, log=None)
        err(f"Description updated from {item_label}")

    # Sync comments (default enabled, skip if --no-comments)
    new_comments = 0
    updated_comments = 0
    if not no_comments:
        err("Syncing comments from remote...")
        # Get item type
        item_type = proc.line('git', 'config', 'pr.type', err_ok=True, log=None)
        if not item_type:
            _, item_type = get_item_metadata(owner, repo, pr_number)

        remote_comments = get_item_comments(owner, repo, pr_number, item_type)
        if remote_comments:
            existing_files = glob('z*.md')
            # Map comment ID to filename
            existing_id_to_file = {get_comment_id_from_filename(f): f for f in existing_files if get_comment_id_from_filename(f)}

            for comment in remote_comments:
                comment_id = str(comment['id'])
                author = comment['user']['login']
                created_at = comment['created_at']
                updated_at = comment.get('updated_at')
                body = comment.get('body', '')

                if comment_id in existing_id_to_file:
                    # Use the actual filename (which includes author)
                    existing_file = existing_id_to_file[comment_id]
                    comment_file = Path(existing_file)
                    _, _, _, local_body = read_comment_file(comment_file)
                    if local_body != body:
                        if dry_run:
                            err(f"[DRY-RUN] Would update comment {comment_id}")
                        else:
                            # Write will create z{id}-{author}.md
                            new_file = write_comment_file(comment_id, author, created_at, updated_at, body)
                            # If filename changed (legacy z{id}.md → z{id}-{author}.md), remove old
                            if str(new_file) != existing_file:
                                proc.run('git', 'rm', existing_file, log=None)
                            proc.run('git', 'add', str(new_file), log=None)
                            updated_comments += 1
                else:
                    if dry_run:
                        err(f"[DRY-RUN] Would add comment {comment_id} by {author}")
                    else:
                        comment_file = write_comment_file(comment_id, author, created_at, updated_at, body)
                        proc.run('git', 'add', str(comment_file), log=None)
                        new_comments += 1

            if new_comments > 0:
                err(f"Found {new_comments} new comment(s)")
            if updated_comments > 0:
                err(f"Found {updated_comments} updated comment(s)")
            if new_comments == 0 and updated_comments == 0:
                err("All comments are up to date")
        else:
            err("No comments found remotely")

    # Create single commit with all changes (description + comments)
    if desc_changed or new_comments > 0 or updated_comments > 0:
        if not dry_run:
            # Build commit message
            msg_parts = []
            if desc_changed:
                msg_parts.append('description')
            if new_comments > 0:
                msg_parts.append(f'{new_comments} new comment(s)')
            if updated_comments > 0:
                msg_parts.append(f'{updated_comments} updated comment(s)')

            commit_msg = f'Pull from {item_label}: {", ".join(msg_parts)}'
            proc.run('git', 'commit', '-m', commit_msg, log=None)
            err(f"Committed changes from {item_label}")
        else:
            err(f"[DRY-RUN] Would commit changes from {item_label}")
    else:
        err(f"No changes from {item_label}")

    # Now push our version back
    err(f"Pushing to {item_label}...")
    # Convert pull's footer boolean to push's footer count
    footer_count = 1 if footer else 0 if footer is False else 0
    push_module.push(gist, dry_run, footer_count, no_footer=False, open_browser=open_browser, images=False, gist_private=gist_private, no_comments=no_comments, force_others=False)


def register(cli):
    """Register command with CLI."""

    @cli.command()
    @flag('--no-comments', help='Skip syncing comments')
    @opt('-p/-P', '--private/--public', 'gist_private', default=None, help='Gist visibility: -p = private, -P = public (default: match repo visibility)')
    @flag('-o', '--open', 'open_browser', help='Open PR in browser after pulling')
    @opt('-f/-F', '--footer/--no-footer', default=None, help='Add gist footer to PR (default: auto - add if gist exists)')
    @flag('-n', '--dry-run', help='Show what would be done')
    @flag('-g', '--gist', help='Also sync to gist')
    def pull_cmd(no_comments, gist_private, open_browser, footer, dry_run, gist):
        pull(gist, dry_run, footer, open_browser, gist_private, no_comments)
