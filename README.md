# ghpr

"Clone" GitHub PRs/issues, locally edit title/description/comments, "push" back to GitHub, and mirror to Gists.

[![ghpr-py](https://img.shields.io/pypi/v/ghpr-py?label=ghpr-py)](https://pypi.org/project/ghpr-py/)

- Sometimes PR and issue descriptions/comments warrant more complex editing than GitHub's web UI comfortably allows.
- `ghpr` lets you "clone" PRs and issues locally as Markdown files (including titles and comments), so you can edit them with your favorite IDE, then "push" updates back to GitHub.
- `ghpr` also mirrors PR/issue content to Gists, for version control and easy sharing / backing up / syncing across machines.

**Examples:**
- [marin#1773]: issue with complex description and comments ([e.g.][1773 comment]); mirrored to [this gist][1773 gist]
- [marin#1723]: PR with complex description, mirrored to [this gist][1723 gist]

## Features

- **Clone** PR/Issues locally with comments
- **Sync** bidirectionally between GitHub and local files
- **Diff** local changes vs remote (with ownership warnings for others' comments)
- **Push** updates back to GitHub
- **Gist mirroring** for version control and sharing
- **Comment management** - edit and sync PR/issue comments
- **Draft comments** - create `new*.md` files, push to post as comments

## Installation

```bash
pip install ghpr-py
```

## Usage

### Basic Workflow

```bash
# Clone a PR or issue (to `gh/123` by default
ghpr clone https://github.com/owner/repo/pull/123
# or
ghpr clone owner/repo#123

# Make edits to:
# - Title / Description: `gh/123/repo#123.md`
# - Comment files: `zNNNNNN-<author>.md` (existing comments) or `new.md` (new comments)

# Show differences (between local "clone" and GitHub)
ghpr diff

# Push changes
ghpr push
```

### Adding Comments

To add a new comment, create a file starting with `new` and ending in `.md`:

```bash
# Create a draft comment
echo "My comment text" > new.md

# Commit it
git add new.md
git commit -m "Draft comment"

# Push to GitHub (posts the comment and renames to z{id}-{author}.md)
ghpr push
```

The `push` command will:
1. Post `new*.md` files as comments to GitHub
2. Create a commit renaming them to `z{comment_id}-{author}.md`
3. Sync to the gist mirror

### Uploading Images

```bash
# Upload image(s) to this issue or PR's Gist mirror, and get markdown URLs
ghpr upload screenshot.png
# Output: ![screenshot.png](https://gist.githubusercontent.com/...)
```

**Note:** GitHub serves gist raw files as `application/octet-stream`, so images render in markdown but videos won't preview inline. For videos, use GitHub's native drag-drop upload in the web UI instead.

## Directory Structure

Cloned PRs and issues are stored as:
```
gh/123/
  repo#123.md             # Main description
  z3404494861-user.md     # Comments (ID-author format)
  z3407382913-user.md
```

Since PRs are issues in GitHub's API, we use the same `gh/{number}/` pattern for both.

## Shell Integration (Optional)

For users who want shorter aliases, `ghpr` provides shell integration:

### Bash/Zsh

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
eval "$(ghpr shell-integration bash)"
```

### Fish

Add to your `~/.config/fish/config.fish`:

```fish
ghpr shell-integration fish | source
```

### Available Aliases

After enabling shell integration, you get convenient shortcuts:

```bash
ghpri      # ghpr init
ghpro      # ghpr open
ghprog     # ghpr open -g
ghprcr     # ghpr create
ghprsh     # ghpr show
ghprc      # ghpr clone
ghprp      # ghpr push
ghprl      # ghpr pull
ghprd      # ghpr diff
# ... and more
```

See the full list with:
```bash
ghpr shell-integration bash
```

[marin#1773]: https://github.com/marin-community/marin/issues/1773
[1773 comment]: https://github.com/marin-community/marin/issues/1773#issuecomment-3478991552
[1773 gist]: https://gist.github.com/ryan-williams/857fcaa8b2f80a250a70ac0250634ee5
[marin#1723]: https://github.com/marin-community/marin/pull/1723
[1723 gist]: https://gist.github.com/f38c0ab59897cfb57c99081b7d87af54
