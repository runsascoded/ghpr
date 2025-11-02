# PyPI Publishing Setup

This project uses **Trusted Publishing** (OIDC) to publish to PyPI and TestPyPI without storing API tokens.

## Initial Setup

### 1. Create PyPI Account
If you don't have one: https://pypi.org/account/register/

### 2. Reserve Package Name (Optional but Recommended)
Reserve `ghpr-py` on PyPI before setting up trusted publishing:
- Go to https://pypi.org/manage/account/publishing/
- "Add a new pending publisher"
- Fill in:
  - **PyPI Project Name**: `ghpr-py`
  - **Owner**: `runsascoded`
  - **Repository name**: `ghpr`
  - **Workflow name**: `release.yml`
  - **Environment name**: (leave empty)

### 3. Set up TestPyPI (for testing releases)
Same process at https://test.pypi.org/manage/account/publishing/:
- **PyPI Project Name**: `ghpr-py`
- **Owner**: `runsascoded`
- **Repository name**: `ghpr`
- **Workflow name**: `release.yml`
- **Environment name**: (leave empty)

## Release Process

### Testing with TestPyPI
Use release candidate tags (containing `rc`):
```bash
git tag -a v0.1.0-rc1 -m "Release candidate 1"
git push origin v0.1.0-rc1
```
This publishes to TestPyPI only.

### Production Release to PyPI
Use stable version tags (no `rc`):
```bash
git tag -a v0.1.0 -m "Initial stable release"
git push origin v0.1.0
```
This publishes to PyPI and creates a GitHub Release.

## Testing Installation from TestPyPI

After publishing to TestPyPI:
```bash
# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ ghpr-py

# Test it works
ghpr --help
```

Note: The `--extra-index-url` is needed because TestPyPI doesn't have all dependencies.

## How Trusted Publishing Works

GitHub Actions automatically authenticates with PyPI using OIDC tokens:
1. Workflow requests OIDC token from GitHub
2. PyPI validates the token against your trusted publisher configuration
3. If valid, allows publishing without API tokens

Benefits:
- ✅ No API tokens to manage or rotate
- ✅ More secure (scoped to specific repo/workflow)
- ✅ Automatic trust establishment

## Troubleshooting

**"Trusted publishing not configured"**
- Make sure you've added the pending publisher on PyPI/TestPyPI
- Verify the repository owner, name, and workflow name match exactly

**"Package name already exists"**
- The name `ghpr-py` is already reserved for this project
- If publishing to TestPyPI first, that's expected

**Dependencies not found when installing from TestPyPI**
- Use both index URLs: `--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/`
