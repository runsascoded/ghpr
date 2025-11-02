# ghpr Development Guide

This document provides context for Claude Code when continuing development on `ghpr`.

## Project Overview

`ghpr` (GitHub PR) is a CLI tool for managing GitHub PRs and Issues locally with bidirectional sync and gist mirroring.

**PyPI Package**: `ghpr-py` (reserved)
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
- ✅ PyPI name `ghpr-py` reserved
- ✅ Repository created with filtered history (23 commits preserved)
- ✅ Package structure initialized

### File Structure (Current)
```
~/c/ghpr/
├── ghpr.py              # Monolithic 2800+ line script
├── pyproject.toml       # Package metadata
├── README.md
└── src/ghpr/
    └── __init__.py
```

## Pending Tasks

### 1. Change Directory Structure: `issue{num}/` → `gh/{num}/`

**Current**: Clones create `pr123/` or `issue123/` directories
**Goal**: Use `gh/123/` for both PRs and issues (since PRs are issues)

**Rationale**:
- GitHub redirects PR URLs to `/issues/` anyway
- PRs **are** issues with extra features
- Simpler mental model (one pattern vs two)
- The `item_type` config tracks whether it's a PR or issue for API calls

**Changes needed**:
- Update `clone` command default directory logic
- Search for `pr{number}` and `issue{number}` patterns in code
- Update documentation

### 2. Comment Filename Format: `z{id}.md` → `z{id}-{author}.md`

**Current**: `z3404494861.md`
**Goal**: `z3404494861-ryan-williams.md`

**Benefits**:
- Immediately visible who wrote each comment in file listings
- Preserves chronological sort (ID first)
- Better UX in `tree` views

**Implementation**:
- Update `write_comment_file()` to include author in filename
- Update `get_comment_id_from_filename()` to handle new format (strip `-{author}.md`)
- Update `read_comment_file()` to parse new format
- Consider backward compat for existing `z{id}.md` files

### 3. Remove `sync` Command

The `sync` command (lines ~2248-2640 in `ghpr.py`) was originally for migrating old `DESCRIPTION.md` format to new `{repo}#{num}.md` format. This migration is obsolete.

**Action**: Delete the entire `sync` command and its implementation.

### 4. Implement `ghpr comment` Command

**Purpose**: Add a new comment to an existing issue/PR from a local draft file.

**Usage**:
```bash
# Draft a comment
echo "My thoughts..." > draft.md

# Post it
ghpr comment draft.md
# or infer the file (must be exactly one uncommitted .md that's not a comment/description)
ghpr comment
```

**Workflow**:
1. Find the draft `.md` file:
   - If path provided: use it
   - If no path: find exactly one `.md` file that's not `{repo}#{num}.md` or `z*.md`
   - File can be untracked, uncommitted, or committed
   - Error if ambiguous (multiple candidates)
2. Post comment to GitHub via `gh api`
3. Fetch the new comment back to get its ID
4. Rename draft to `z{comment_id}-{current_user}.md`
5. Commit and push to gist

**Implementation hints**:
- Use `get_current_github_user()` helper
- Use `gh api` POST to `/repos/{owner}/{repo}/issues/{number}/comments`
- Response includes `id` field
- Use `write_comment_file()` after renaming

### 5. Refactor into Modules

**Current**: Single 2800+ line `ghpr.py` file
**Goal**: Modular package structure

**Proposed structure**:
```
src/ghpr/
├── __init__.py
├── cli.py          # Click command definitions
├── api.py          # GitHub API helpers
├── gist.py         # Gist operations
├── comments.py     # Comment file read/write
├── files.py        # Description file operations
└── config.py       # Git config helpers
```

**Migration strategy**:
1. Keep `ghpr.py` as entry point initially
2. Extract helper functions into modules
3. Update imports
4. Move CLI commands to `cli.py`
5. Update `pyproject.toml` entry point to `ghpr.cli:cli`
6. Eventually deprecate/remove top-level `ghpr.py`

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
comments = proc.json('gh', 'api', f'repos/{owner}/{repo}/issues/{number}/comments', log=None)

# Post comment
proc.run('gh', 'api', '-X', 'POST', f'repos/{owner}/{repo}/issues/{number}/comments',
         '-f', f'body=@{temp_file}', log=None)
```

## Testing

Test with the example issue:
```bash
cd ~/c/oa/marin/issue1773  # Existing test case
# Or clone fresh:
ghpr clone https://github.com/marin-community/marin/issues/1773
```

## Related Files

- `utz` library: Used for `proc` (subprocess), `err` (stderr output), `cd` (context manager)
- Helper functions in `git_helpers` module (imported from parent repo)

## Dependencies

```toml
dependencies = [
    "click>=8.0",   # CLI framework
    "utz>=0.1.0",   # Subprocess and utility helpers
]
```

## Notes

- Original author email: `ryan@runsascoded.com`
- History preserved from `ryan-williams/git-helpers` repo
- The `z` prefix on comment files ensures they sort after the main description
