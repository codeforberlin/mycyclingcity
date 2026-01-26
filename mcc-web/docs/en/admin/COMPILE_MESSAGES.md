# Compiling Translations (without venv libraries)

By default, `python manage.py compilemessages` compiles **all** found `.po` files, including those from installed libraries in the venv. This is usually not necessary and can save time.

## Solution: Compile Only Project Translations

### Method 1: Use Makefile (Recommended)

```bash
make compilemessages
```

This compiles only translations for `de` and `en` from the project directory (`locale/`).

### Method 2: Use Script

```bash
./scripts/compilemessages_project_only.sh
```

Or for a specific language:

```bash
./scripts/compilemessages_project_only.sh de
./scripts/compilemessages_project_only.sh en
```

### Method 3: Direct with manage.py (specific languages only)

```bash
python manage.py compilemessages --locale de --locale en
```

This compiles only the specified languages and automatically ignores venv libraries, since `LOCALE_PATHS` in `settings.py` only points to `BASE_DIR / 'locale'`.

### Method 4: Custom Management Command

```bash
python manage.py compilemessages_custom
```

This command compiles only translations from `LOCALE_PATHS` and explicitly excludes venv directories.

## Why does this work?

In `config/settings.py`, `LOCALE_PATHS` is already correctly configured:

```python
LOCALE_PATHS = [
    BASE_DIR / 'locale',  # Only project directory
]
```

When you use `compilemessages` with `--locale`, only translations from `LOCALE_PATHS` for the specified languages are compiled.

## Change Default Behavior

If you want `compilemessages` to compile only project translations by default, you can:

1. **Create alias** (in `~/.bashrc` or `~/.zshrc`):
   ```bash
   alias compilemessages='python manage.py compilemessages --locale de --locale en'
   ```

2. **Use Makefile** (already set up):
   ```bash
   make compilemessages
   ```

## Compile All Translations (including venv)

If you want to compile all translations (e.g., for debugging):

```bash
make compilemessages-all
# or
python manage.py compilemessages
```

## Verification

Check which `.mo` files were created:

```bash
# Only project translations
find locale/ -name "*.mo"

# All translations (including venv)
find . -name "*.mo" -not -path "*/venv/*" -not -path "*/__pycache__/*"
```

The first search should only find files in `locale/` if you used `--locale`.
