#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Script to fix SQLite NFS issues by moving database to local filesystem
#
# Usage:
#   ./scripts/fix_sqlite_nfs.sh [--backup-dir=/path/to/backup]
#
# This script:
# 1. Stops Gunicorn
# 2. Backs up the database
# 3. Moves database to local filesystem (/var/lib/mcc-db)
# 4. Creates symlink
# 5. Updates settings.py (optional)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"

# Get database path from Django settings dynamically
get_db_path() {
    python3 -c "
import os
import sys
sys.path.insert(0, '$PROJECT_DIR')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
print(settings.DATABASES['default']['NAME'])
" 2>/dev/null || echo "$PROJECT_DIR/data/db.sqlite3"
}

DB_FILE="$(get_db_path)"
LOCAL_DB_DIR="/var/lib/mcc-db"
LOCAL_DB_FILE="$LOCAL_DB_DIR/$(basename "$DB_FILE")"

echo "=========================================="
echo "SQLite NFS Fix Script"
echo "=========================================="
echo ""

# Check if running as root (needed for /var/lib)
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Warning: This script should be run as root to create /var/lib/mcc-db"
    echo "   You can also use a different directory (set LOCAL_DB_DIR environment variable)"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    # Use user's home directory instead
    LOCAL_DB_DIR="$HOME/.mcc-db"
    LOCAL_DB_FILE="$LOCAL_DB_DIR/$(basename "$DB_FILE")"
fi

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    echo "❌ Error: Database file not found: $DB_FILE"
    exit 1
fi

# Check if database is on NFS
DB_MOUNT=$(df "$DB_FILE" | tail -1 | awk '{print $1}')
if [[ ! "$DB_MOUNT" =~ ^/dev/ ]]; then
    echo "✅ Database is on NFS: $DB_MOUNT"
    echo "   This script will move it to local filesystem"
else
    echo "ℹ️  Database is already on local filesystem: $DB_MOUNT"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

# Stop Gunicorn
echo ""
echo "1. Stopping Gunicorn..."
if pgrep -f gunicorn > /dev/null; then
    pkill -f gunicorn
    sleep 2
    if pgrep -f gunicorn > /dev/null; then
        echo "⚠️  Warning: Gunicorn still running, forcing kill..."
        pkill -9 -f gunicorn
        sleep 1
    fi
    echo "✅ Gunicorn stopped"
else
    echo "ℹ️  Gunicorn not running"
fi

# Create backup
echo ""
echo "2. Creating backup..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/db_backup_$(date +%Y%m%d_%H%M%S).sqlite3"
cp "$DB_FILE" "$BACKUP_FILE"
echo "✅ Backup created: $BACKUP_FILE"

# Create local directory
echo ""
echo "3. Creating local database directory..."
mkdir -p "$LOCAL_DB_DIR"
chmod 755 "$LOCAL_DB_DIR"
echo "✅ Directory created: $LOCAL_DB_DIR"

# Move database
echo ""
echo "4. Moving database to local filesystem..."
if [ -f "$LOCAL_DB_FILE" ]; then
    echo "⚠️  Warning: Local database already exists: $LOCAL_DB_FILE"
    read -p "Overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted"
        exit 1
    fi
fi

mv "$DB_FILE" "$LOCAL_DB_FILE"
chmod 644 "$LOCAL_DB_FILE"
echo "✅ Database moved to: $LOCAL_DB_FILE"

# Create symlink
echo ""
echo "5. Creating symlink..."
ln -sf "$LOCAL_DB_FILE" "$DB_FILE"
echo "✅ Symlink created: $DB_FILE -> $LOCAL_DB_FILE"

# Verify
echo ""
echo "6. Verifying..."
if [ -L "$DB_FILE" ] && [ -f "$LOCAL_DB_FILE" ]; then
    echo "✅ Symlink is valid"
    echo "✅ Database file exists"
    echo ""
    echo "=========================================="
    echo "✅ Migration completed successfully!"
    echo "=========================================="
    echo ""
    echo "Database location: $LOCAL_DB_FILE"
    echo "Symlink: $DB_FILE"
    echo "Backup: $BACKUP_FILE"
    echo ""
    echo "Next steps:"
    echo "1. Start Gunicorn with multiple workers:"
    echo "   gunicorn --workers 5 --threads 2 --bind 0.0.0.0:8001 config.wsgi:application"
    echo ""
    echo "2. Test the application"
    echo ""
    echo "3. Update settings.py (optional) to use absolute path:"
    echo "   'NAME': '$LOCAL_DB_FILE',"
else
    echo "❌ Error: Verification failed"
    echo "   Restoring from backup..."
    mv "$BACKUP_FILE" "$DB_FILE"
    exit 1
fi
