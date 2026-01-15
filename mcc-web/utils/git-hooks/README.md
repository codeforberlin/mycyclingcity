# Git Hooks for Version Management

This directory contains example Git hooks for automatically managing `version.txt`.

## Available Hooks

### post-receive.example
Generates `version.txt` when a tag is pushed to the repository.

**Installation:**
```bash
cp utils/git-hooks/post-receive.example .git/hooks/post-receive
chmod +x .git/hooks/post-receive
```

### pre-push.example
Automatically updates `version.txt` before pushing to ensure it's always in sync with git.

**Installation:**
```bash
cp utils/git-hooks/pre-push.example .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

## Manual Usage

You can also generate `version.txt` manually:

```bash
# Auto-detect from git
python utils/generate_version.py

# Set specific version
python utils/generate_version.py --version 1.2.3

# Use current git tag
python utils/generate_version.py --tag
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Generate Version

on:
  push:
    tags:
      - 'v*'

jobs:
  generate-version:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Fetch all history for git describe
      
      - name: Generate version.txt
        run: |
          cd mcc-web
          python utils/generate_version.py --tag
      
      - name: Commit version.txt
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add mcc-web/version.txt
          git commit -m "chore: update version.txt" || exit 0
          git push
```

### GitLab CI Example

```yaml
generate_version:
  stage: build
  only:
    - tags
  script:
    - cd mcc-web
    - python utils/generate_version.py --tag
    - git add version.txt
    - git commit -m "chore: update version.txt" || true
    - git push
```
