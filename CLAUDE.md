# ghpr Development Guide

This document provides context for Claude Code when continuing development on `ghpr`.

## Project Overview

`ghpr` (GitHub PR) is a CLI tool for managing GitHub PRs and Issues locally with bidirectional sync and gist mirroring.

**PyPI Package**: `ghpr-py` (published)
**Repository**: https://github.com/runsascoded/ghpr
**Command**: `ghpr`

## Core Workflow

```
GitHub Issue/PR ↔ Local Clone → Gist (read replica/mirror)
```

The gist is a **read replica** of the local clone. `push`/`pull` operations sync between local and GitHub, and the gist is automatically updated to mirror local state.

## Current State

### Completed
- ✅ Basic clone/push/pull/diff commands
- ✅ Comment support (fetch, diff, push comments)
- ✅ Gist mirroring
- ✅ Issue and PR support
- ✅ Comments default enabled (with `--no-comments` opt-out)
- ✅ Directory structure: `gh/{num}/` for both PRs and issues
- ✅ Comment filename format: `z{id}-{author}.md`
- ✅ Draft comment workflow: `new*.md` → post → rename
- ✅ Unified diff display between `diff` and `push -n`
- ✅ Image upload command using `utz.git.gist`
- ✅ PyPI package `ghpr-py` published (v0.1.0)
- ✅ Repository created with filtered history
- ✅ Modular package structure (commands in separate modules)
- ✅ Using published `utz>=0.21.3` for git utilities

### File Structure (Current)
```
~/c/ghpr/
├── pyproject.toml       # Package metadata
├── README.md
├── CLAUDE.md           # This file
├── ghpr.py             # Standalone uv run script
└── src/ghpr/
    ├── __init__.py
    ├── cli.py          # Main CLI entry point, registers commands
    ├── api.py          # GitHub API helpers
    ├── gist.py         # Gist operations
    ├── comments.py     # Comment file read/write
    ├── files.py        # Description file operations
    ├── config.py       # Git config helpers
    ├── patterns.py     # Regex patterns
    ├── render.py       # Diff rendering utilities
    └── commands/       # Modular command implementations
        ├── clone.py
        ├── create.py
        ├── diff.py
        ├── ingest_attachments.py
        ├── open.py
        ├── pull.py
        ├── push.py
        ├── shell_integration.py
        ├── show.py
        └── upload.py
```

### Recent Changes

**Draft Comment Workflow** (completed):
- Create files starting with `new` and ending in `.md` (e.g., `new.md`, `new-feature.md`)
- Commit them to git
- `ghpr push` automatically:
  1. Posts them as comments to GitHub
  2. Creates a commit renaming `new*.md` → `z{comment_id}-{author}.md`
  3. Syncs to gist
- Handles local modifications gracefully (uses `git rm -f`)

**Unified Diff Display** (completed):
- Both `diff` and `push -n` show identical output
- Draft comments displayed in green
- Comment changes shown with unified diff
- Metadata (line counts, etc.) in bold

**Image Upload** (completed):
- `ghpr upload <file>` uploads to gist and returns markdown URLs
- Uses `utz.git.gist` module for shared functionality
- Auto-formats as markdown for images, URL for other files

## Key Design Principles

1. **Gist as read replica**: Gist always mirrors local state, never the source of truth
2. **Comments by default**: Comment operations are core functionality, not optional
3. **Fail fast**: Better to error on ambiguity than guess wrong
4. **Git as storage**: Use git commits for versioning, leverage existing git workflows
5. **Prefer existing tools**: Use `gh` CLI for API operations, `git` for VCS

## Code Patterns

### Error Handling
```python
if not all([owner, repo, number]):
    err("Error: Could not determine PR/Issue from directory")
    exit(1)
```

### Git Config Storage
```python
proc.run('git', 'config', 'pr.owner', owner, log=None)
item_type = proc.line('git', 'config', 'pr.type', err_ok=True, log=None)
```

### Comment File Format
```markdown
<!-- author: ryan-williams -->
<!-- created_at: 2025-10-15T04:38:13Z -->
<!-- updated_at: 2025-10-15T04:38:13Z -->

Comment body here...
```

### API Patterns
```python
# Fetch comments
comments = proc.json('gh', 'api', f'repos/{owner}/{repo}/issues/{number}/comments', log=False)

# Post comment (use -F with body=@file to read from file)
result = proc.json(
    'gh', 'api',
    '-X', 'POST',
    f'repos/{owner}/{repo}/issues/{number}/comments',
    '-F', f'body=@{temp_file}',
    log=False
)
```

## Testing

Test with the example issue:
```bash
cd ~/c/oa/marin/issue1773  # Existing test case
# Or clone fresh:
ghpr clone https://github.com/marin-community/marin/issues/1773
```

## Related Files

- `utz` library: Used for `proc` (subprocess), `err` (stderr output), `cd` (context manager), and git utilities

## Dependencies

```toml
dependencies = [
    "click>=8.0",    # CLI framework
    "utz>=0.21.3",   # Subprocess and git utility helpers
]
```

## Notes

- Original author email: `ryan@runsascoded.com`
- History preserved from `ryan-williams/git-helpers` repo
- The `z` prefix on comment files ensures they sort after the main description
