"""GitHub API helpers for fetching PR/Issue data."""

from utz import proc, err


def get_item_metadata(owner: str, repo: str, number: str, item_type: str | None = None) -> tuple[dict | None, str]:
    """Get PR or Issue metadata from GitHub.

    Returns:
        Tuple of (metadata dict, item_type) where item_type is 'pr' or 'issue'
    """
    # Try to detect type if not specified
    if not item_type:
        # Try PR first (use err_ok to suppress GraphQL errors for issues)
        try:
            from subprocess import DEVNULL
            data = proc.json('gh', 'pr', 'view', number, '-R', f'{owner}/{repo}', '--json', 'title,body,number,url', log=False, stderr=DEVNULL)
            # Normalize line endings from GitHub (convert \r\n to \n)
            if data.get('body'):
                data['body'] = data['body'].replace('\r\n', '\n')
            return data, 'pr'
        except Exception:
            # Try issue
            try:
                data = proc.json('gh', 'issue', 'view', number, '-R', f'{owner}/{repo}', '--json', 'title,body,number,url', log=False)
                if data.get('body'):
                    data['body'] = data['body'].replace('\r\n', '\n')
                return data, 'issue'
            except Exception as e:
                err(f"Error fetching PR/Issue metadata: {e}")
                return None, item_type or 'pr'

    # Use specified type
    cmd = 'pr' if item_type == 'pr' else 'issue'
    try:
        data = proc.json('gh', cmd, 'view', number, '-R', f'{owner}/{repo}', '--json', 'title,body,number,url', log=False)
        # Normalize line endings from GitHub (convert \r\n to \n)
        if data.get('body'):
            data['body'] = data['body'].replace('\r\n', '\n')
        return data, item_type
    except Exception as e:
        err(f"Error fetching {item_type} metadata: {e}")
        return None, item_type


def get_pr_metadata(owner: str, repo: str, pr_number: str) -> dict | None:
    """Legacy function for backwards compatibility."""
    data, _ = get_item_metadata(owner, repo, pr_number, 'pr')
    return data


def get_current_github_user() -> str | None:
    """Get the currently authenticated GitHub user."""
    from utz.git.gist import get_github_user
    return get_github_user()


def get_item_comments(owner: str, repo: str, number: str, item_type: str) -> list[dict]:
    """Fetch all comments for a PR or Issue from GitHub.

    Returns:
        List of comment dicts with keys: id, user.login, created_at, updated_at, body
    """
    try:
        if item_type == 'pr':
            comments = proc.json('gh', 'api', f'repos/{owner}/{repo}/issues/{number}/comments', log=False)
        else:
            comments = proc.json('gh', 'api', f'repos/{owner}/{repo}/issues/{number}/comments', log=False)

        # Normalize line endings in comment bodies
        for comment in comments:
            if comment.get('body'):
                comment['body'] = comment['body'].replace('\r\n', '\n')

        return comments
    except Exception as e:
        err(f"Error fetching comments: {e}")
        return []
