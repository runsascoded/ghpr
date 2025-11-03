# ghpr

GitHub PR/Issue management tool for local iteration with gist mirroring.

## Features

- **Clone** PR/Issues locally with comments
- **Sync** bidirectionally between GitHub and local files
- **Diff** local changes vs remote
- **Push** updates back to GitHub
- **Gist mirroring** for version control and sharing
- **Comment management** - edit and sync PR/issue comments

## Installation

```bash
pip install ghpr-py
```

## Usage

### Basic Workflow

```bash
# Clone a PR or issue
ghpr clone https://github.com/owner/repo/pull/123
# or
ghpr clone owner/repo#123

# Show differences
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
# Upload image(s) to the gist and get markdown URLs
ghpr upload screenshot.png
# Output: ![screenshot.png](https://gist.githubusercontent.com/...)
```

## Directory Structure

Cloned PRs and issues are stored as:
```
gh/123/
  owner-repo#123.md       # Main description
  z3404494861-user.md     # Comments (ID-author format)
  z3407382913-user.md
```

Since PRs are issues in GitHub's API, we use the same `gh/{number}/` pattern for both.

## Shell Integration (Optional)

For power users who want shorter aliases, `ghpr` provides shell integration:

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

## Development

Repository: [runsascoded/ghpr](https://github.com/runsascoded/ghpr)
