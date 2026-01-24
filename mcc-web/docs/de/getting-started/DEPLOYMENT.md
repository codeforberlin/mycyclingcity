# Deployment Guide

This guide explains how to create a deployment archive and deploy the MCC-Web application to production.

## Overview

The deployment process consists of two main steps:

1. **Create Deployment Archive**: Package all necessary files into a tar.gz archive
2. **Deploy to Production**: Initialize or update the production system

## Step 1: Create Deployment Archive

Use `utils/create_deployment_archive.py` to create a deployment package.

### Usage

```bash
# Basic usage (creates archive in project root)
python utils/create_deployment_archive.py

# Specify output directory
python utils/create_deployment_archive.py -o /path/to/output

# Or run directly
./utils/create_deployment_archive.py
```

### What's Included

The archive contains:
- All Python source files
- Templates
- Static file sources (not `staticfiles/` - will be generated on server)
- Database migrations
- Translation files (`.po` files)
- `requirements.txt`
- `manage.py`
- Configuration files
- README and documentation

### What's Excluded

The archive automatically excludes:
- `__pycache__/` directories
- `staticfiles/` (generated on server)
- `media/` (user-generated content)
- Database files (`data/db.sqlite3*`)
- Compiled translation files (`.mo` - will be generated)
- Virtual environments
- IDE files
- Test files and coverage reports
- Git repository

### Archive Naming

Archives are named: `mcc-web-deployment-{version}-{timestamp}.tar.gz`

The version is determined from:
1. `version.txt` file (if exists)
2. Git tag/describe (fallback)
3. "dev" (if neither available)

### Generating version.txt

You can generate `version.txt` automatically using:

```bash
# Auto-detect from git
python utils/generate_version.py
# Or using make
make version

# Set specific version
python utils/generate_version.py --version 1.2.3

# Use current git tag (if HEAD is on a tag)
python utils/generate_version.py --tag

# Remove version.txt (fallback to git describe)
python utils/generate_version.py --clean
# Or using make
make version-clean
```

## Step 2: Deploy to Production

Use `utils/deploy_production.py` to deploy the application on the production server.

### Prerequisites

1. Extract the deployment archive on the production server
2. Set up Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Usage

```bash
# Full deployment (recommended)
python utils/deploy_production.py

# Skip backup (not recommended for production)
python utils/deploy_production.py --skip-backup

# Clear static files before collecting
python utils/deploy_production.py --clear-static

# Skip static file collection (if already done)
python utils/deploy_production.py --skip-static

# Skip translation compilation
python utils/deploy_production.py --skip-compilemessages
```

### What the Script Does

The deployment script performs the following steps in order:

1. **Environment Check**: Validates Django environment
2. **Database Backup**: Creates backup of existing database (if exists)
   - Backups are stored in `backups/` directory
   - Includes database file and WAL/SHM files
   - Timestamped: `db_backup_YYYYMMDD_HHMMSS.sqlite3`
3. **Database Migration**: Runs Django migrations
   - Initializes database if it doesn't exist
   - Updates schema if database exists
4. **Static Files**: Collects static files using `collectstatic`
   - Required for production (Apache serves from `staticfiles/`)
5. **Translations**: Compiles translation messages (`.po` → `.mo`)
6. **Validation**: Performs basic validation checks

### Safety Features

- **Automatic Backup**: Database is backed up before any migration
- **Error Handling**: Script stops on critical errors
- **Validation**: Checks are performed after deployment
- **User Confirmation**: Prompts for confirmation if backup fails

### Command Line Options

| Option | Description |
|--------|-------------|
| `--project-dir DIR` | Project root directory (default: current directory) |
| `--skip-backup` | Skip database backup (not recommended) |
| `--skip-static` | Skip static file collection |
| `--skip-compilemessages` | Skip translation compilation |
| `--clear-static` | Clear existing static files before collecting |
| `--fake-initial` | Mark initial migrations as applied without running |

## Complete Deployment Workflow

### On Development Machine

```bash
# 1. Create deployment archive
python utils/create_deployment_archive.py

# 2. Transfer archive to production server
scp mcc-web-deployment-*.tar.gz user@production-server:/tmp/
```

### On Production Server

```bash
# 1. Navigate to application directory
cd /data/games/mcc/mcc-web

# 2. Extract archive
tar xzf /tmp/mcc-web-deployment-*.tar.gz

# 3. Activate virtual environment
source venv/bin/activate

# 4. Install/update dependencies (if needed)
pip install -r requirements.txt

# 5. Run deployment script
python utils/deploy_production.py

# 6. Restart application server (script)
/data/games/mcc/mcc-web/scripts/mcc-web.sh restart
```

## Important Notes

### Database Backups

- Backups are stored in `backups/` directory in the project root
- Keep multiple backups for rollback capability
- Consider implementing automated backup rotation

### Static Files

- Static files **must** be collected on the production server
- The `staticfiles/` directory is served by Apache, not Django
- Use `--clear-static` if you want to remove old static files

### Media Files

- The `media/` directory contains user-uploaded content
- **Never** overwrite `media/` during deployment
- Ensure proper backup of media files separately

### Environment Variables

Make sure these environment variables are set (via `.env` file or system):

- `SECRET_KEY`: Django secret key
- `DEBUG`: Set to `False` for production
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts
- `CSRF_TRUSTED_ORIGINS`: HTTPS origins for CSRF protection
- Other application-specific variables (see `config/settings.py`)

### Permissions

Ensure proper file permissions:
- Application files: readable by web server user
- `media/` directory: writable by web server user
- Database file: readable/writable by web server user

## Troubleshooting

### Migration Fails

- Check database backup was created
- Verify database file permissions
- Check Django logs for specific error messages
- Consider restoring from backup if needed

### Static Files Not Updating

- Use `--clear-static` flag to force refresh
- Check `STATIC_ROOT` setting in `config/settings.py`
- Verify Apache configuration points to correct `staticfiles/` directory

### Translation Issues

- Ensure `.po` files are included in archive
- Run `compilemessages` manually if needed: `python manage.py compilemessages`
- Check `LOCALE_PATHS` setting

## Rollback Procedure

If deployment fails or issues are discovered:

1. **Stop the application server**
2. **Restore database from backup**:
   ```bash
   cp backups/db_backup_YYYYMMDD_HHMMSS.sqlite3 data/db.sqlite3
   ```
3. **Restore previous code version** (if needed)
4. **Restart application server**

## Additional Resources

- Django Deployment Checklist: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
- Project README: See `README` file for additional setup information

