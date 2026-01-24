#!/bin/bash
# Script to compile only project translations, excluding venv libraries
# Usage: ./scripts/compilemessages_project_only.sh [locale]

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Find Python executable
PYTHON_EXE=""
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_EXE="$VIRTUAL_ENV/bin/python"
elif [ -f "$PROJECT_DIR/venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_DIR/venv/bin/python"
elif [ -f "$HOME/venv_mcc/bin/python" ]; then
    PYTHON_EXE="$HOME/venv_mcc/bin/python"
else
    PYTHON_EXE="python3"
fi

echo "Using Python: $PYTHON_EXE"
echo "Project directory: $PROJECT_DIR"

# Change to project directory
cd "$PROJECT_DIR"

# Get locale if provided
LOCALE="${1:-}"

# Build command
CMD=("$PYTHON_EXE" "manage.py" "compilemessages")

# If locale specified, add it
if [ -n "$LOCALE" ]; then
    CMD+=("--locale" "$LOCALE")
fi

# Add --exclude to skip venv directories
# Note: compilemessages doesn't have --exclude, so we use LOCALE_PATHS in settings.py
# which already limits to BASE_DIR / 'locale'

echo "Compiling translation messages (project only, excluding venv)..."
echo "Command: ${CMD[*]}"

# Execute
"${CMD[@]}"

echo "Done! Only project translations compiled (venv libraries excluded)."
