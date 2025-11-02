"""Comment file read/write operations."""

from pathlib import Path


def write_comment_file(comment_id: str, author: str, created_at: str, updated_at: str | None, body: str) -> Path:
    """Write a comment to a z{comment_id}-{author}.md file.

    Returns:
        Path to the created file
    """
    filename = f'z{comment_id}-{author}.md'
    filepath = Path(filename)

    content_lines = [
        f'<!-- author: {author} -->',
        f'<!-- created_at: {created_at} -->',
    ]

    if updated_at and updated_at != created_at:
        content_lines.append(f'<!-- updated_at: {updated_at} -->')

    content_lines.extend(['', body.rstrip(), ''])

    with open(filepath, 'w') as f:
        f.write('\n'.join(content_lines))

    return filepath


def read_comment_file(filepath: Path) -> tuple[str | None, str | None, str | None, str]:
    """Parse a comment file and extract metadata.

    Returns:
        Tuple of (author, created_at, updated_at, body)
    """
    with open(filepath, 'r') as f:
        lines = f.readlines()

    author = None
    created_at = None
    updated_at = None
    body_start = 0

    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('<!-- author:'):
            author = line.replace('<!-- author:', '').replace('-->', '').strip()
        elif line.startswith('<!-- created_at:'):
            created_at = line.replace('<!-- created_at:', '').replace('-->', '').strip()
        elif line.startswith('<!-- updated_at:'):
            updated_at = line.replace('<!-- updated_at:', '').replace('-->', '').strip()
        elif not line.startswith('<!--'):
            body_start = i
            break

    body = ''.join(lines[body_start:]).strip()
    return author, created_at, updated_at, body


def get_comment_id_from_filename(filename: str) -> str | None:
    """Extract comment ID from z{id}-{author}.md or z{id}.md (legacy) filename."""
    if filename.startswith('z') and filename.endswith('.md'):
        # Remove 'z' prefix and '.md' suffix
        middle = filename[1:-3]
        # Handle new format: z{id}-{author}.md
        if '-' in middle:
            return middle.split('-')[0]
        # Handle legacy format: z{id}.md
        return middle
    return None
