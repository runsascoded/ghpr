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
- ✅ Review-thread sync (inline PR comments): clone/pull threads to flat `gh/<num>/z-<head_id>-<NN>-<author>.md` files (head frontmatter holds thread metadata), edit/reply/resolve locally, push back (REST + GraphQL); `ghpr review reply|resolve|unresolve`
- ✅ Gist mirroring
- ✅ Issue and PR support
- ✅ Comments default enabled (with `--no-comments` opt-out)
- ✅ Directory structure: `gh/{num}/` for both PRs and issues
- ✅ Comment filename format: `z{id}-{author}.md`
- ✅ Draft comment workflow: `new*.md` → post → rename
- ✅ Unified diff display between `diff` and `push -n`
- ✅ Image upload command using `utz.git.gist`
- ✅ Shell completion (Click-powered, subcommands + flags/options on bare `<tab>`)
- ✅ Shell integration with aliases (`ghprc`, `ghprd`, `ghprp`, `ghia`, etc.)
- ✅ Parallel drafts: `ghpr init <slug>` → `gh/drafts/<slug>/`
- ✅ `ghpr clone` auto-detects current branch's PR when no spec given
- ✅ `ghpr create` auto-inits nested git repo (works when parent has `gh/` gitignored)
- ✅ PyPI package `ghpr-py` published
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
├── tests/               # pytest test suite
└── src/ghpr/
    ├── __init__.py
    ├── cli.py          # Main CLI entry point, registers commands
    ├── api.py          # GitHub API helpers
    ├── gist.py         # Gist operations
    ├── comments.py     # Comment file read/write
    ├── reviews.py      # Review-thread (inline comment) pull/push/diff + .thread.yml I/O
    ├── files.py        # Description file operations
    ├── config.py       # Git config helpers
    ├── patterns.py     # Regex patterns
    ├── render.py       # Diff rendering utilities
    ├── shell/          # Shell integration scripts (bash, fish)
    └── commands/       # Modular command implementations
        ├── clone.py
        ├── create.py        # Also contains `init` command
        ├── diff.py
        ├── ingest_attachments.py
        ├── open.py
        ├── pull.py
        ├── push.py
        ├── review.py         # `ghpr review reply|resolve|unresolve` (local edits)
        ├── shell_integration.py
        ├── show.py
        └── upload.py
```

### Recent Changes

**Auto-init nested git repo on `ghpr create`** (latest):
- `_ensure_nested_git_repo()` in `commands/create.py` runs `git init` at the draft dir if it's not already its own git toplevel
- Lets `ghpr create` work even when the parent project has `gh/` in `.gitignore` (the typical setup)
- `git rm DESCRIPTION.md` now uses `-q --ignore-unmatch` so it handles both tracked (existing `ghpr init` repo) and untracked (fresh nested repo) cases

**Parallel drafts under `gh/drafts/<slug>/`**:
- `ghpr init <slug>` and `ghpr create <slug>` resolve to `gh/drafts/<slug>/` (was `gh/new-<slug>/` briefly in v0.1.9)
- Keeps drafts visually separated from filed `gh/<number>/` dirs
- `ghpr init` (no arg) still creates `gh/new/` for back-compat
- Finalize logic walks up to find the `gh/` ancestor, so all layouts rename to `gh/<number>/` on filing

**`ghpr clone` auto-detects branch's PR**:
- `ghprc` (no args) uses `gh pr view` to find the open PR for the current branch and clone it

**Shell Completion**:
- Click-powered tab completion for subcommands, flags, and options
- Patched `Command.shell_complete` and `Argument.shell_complete` in `cli.py` to suggest options on bare `<tab>` (Click only does this when user types `-`)
- Completion script generated inline by `shell_integration.py` (avoids extra Python invocation)
- Click's Bash version warning suppressed (macOS system bash 3.2 triggers it)
- `ghia` alias added for `ghpr ingest-attachments`

**Comment Ownership Warnings**:
- `ghpr diff` and `ghpr push -n` warn when showing diffs for comments authored by others
- `ghpr push` skips others' comments by default, with clear summary message
- Use `-C` (`--force-others`) to attempt pushing edits to others' comments

**Trailing Newline Handling**:
- `write_description_with_link_ref` ensures files always end with a newline
- Fixes diff thrashing when GitHub strips trailing newlines from PR descriptions
- `render_unified_diff` only shows "No newline" indicator when sides actually differ

**Draft Comment Workflow**:
- Create files starting with `new` and ending in `.md` (e.g., `new.md`, `new-feature.md`)
- Commit them to git
- `ghpr push` automatically:
  1. Posts them as comments to GitHub
  2. Creates a commit renaming `new*.md` → `z{comment_id}-{author}.md`
  3. Syncs to gist

**Image Upload**:
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
