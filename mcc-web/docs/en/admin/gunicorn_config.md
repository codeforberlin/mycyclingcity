# Gunicorn Configuration in Admin GUI

## Overview

The Gunicorn log level can now be controlled directly via the Admin Interface without needing to change environment variables.

## Usage

### In Admin GUI

1. **Open Admin GUI**: `/admin/`
2. **Navigation**: "Mgmt" → "Gunicorn Configuration"
3. **Direct URL**: `/admin/mgmt/gunicornconfig/`
4. **Select Log Level**:
   - **DEBUG** - Very detailed output
   - **INFO** - Informative messages (default)
   - **WARNING** - Warnings only
   - **ERROR** - Errors only
   - **CRITICAL** - Critical errors only
5. **Save** - A warning appears that a restart is required

### Server Restart

After changing the log level:

1. Go to `/admin/server/` (Server Control)
2. Click "Restart Server"
3. The new configuration is loaded on startup

## How It Works

### Priority

1. **Database Configuration** (GunicornConfig Model) - **Highest Priority**
   - Managed in Admin GUI
   - Read from database on server startup
   - Passed to Gunicorn as environment variable `GUNICORN_LOG_LEVEL`

2. **Environment Variable** (GUNICORN_LOG_LEVEL) - **Fallback**
   - Only used if database configuration is not available
   - Useful during migrations or when the table doesn't exist yet

3. **Default** - **info**
   - If neither database nor environment variable is available

### Singleton Pattern

GunicornConfig is a singleton model - only one instance exists. On first access, an instance with the default value (info) is automatically created.

## Migration and Setup

### Initial Setup

After migration:

```bash
# Run migration
python manage.py migrate mgmt

# Default value is automatically created (info)
```

### Deployment

The startup script automatically reads the configuration from the database on startup:

```bash
/path/to/mcc-web/scripts/mcc-web.sh start
```

**Note:** 
- **Production**: The application runs under `/data/appl/mcc/mcc-web` as the user configured by the administrator (e.g., `mcc`, `www-data`, etc.)
- **Development**: Paths can be individual, as the application finds all information relative to the project directory
- **User**: The user `mcc` is not mandatory, the user is configured by the administrator

The script uses the management command `get_gunicorn_config` to read the configuration from the database.

## Example Workflow

### Change Log Level

1. In Admin GUI: "Mgmt" → "Gunicorn Configuration"
2. Change log level to "DEBUG"
3. Save
4. Go to "Server Control" (`/admin/server/`)
5. Click "Restart Server"
6. New configuration is loaded

## Important Notes

### ⚠️ Server Restart Required

Changes to the Gunicorn log level require a **server restart** to take effect. The configuration is only loaded on startup.

### 🔄 Immediate Effect

After a restart, the new configuration applies **immediately** to all new log entries.

### 📊 Best Practices

- **Development**: DEBUG or INFO
- **Staging**: INFO or WARNING
- **Production**: WARNING or ERROR
- **Critical Systems**: ERROR or CRITICAL

## Troubleshooting

### Configuration Not Applied

1. Check if migration was executed:
   ```bash
   python manage.py showmigrations mgmt
   ```

2. Check current configuration:
   ```bash
   python manage.py shell
   >>> from mgmt.models import GunicornConfig
   >>> config = GunicornConfig.get_config()
   >>> print(config.log_level)
   ```

3. Check if server was restarted:
   ```bash
   /path/to/mcc-web/scripts/mcc-web.sh status
   ```

4. Check environment variable on startup:
   - Look in `logs/gunicorn_startup.log`
   - The script should show "Using log level from database: X"

### Fallback to Environment Variable

If the database configuration is not available (e.g., during migrations), the system automatically falls back to the `GUNICORN_LOG_LEVEL` environment variable.

## Integration with Server Control

The Gunicorn configuration is integrated into the Server Control page:

- **Server Control** (`/admin/server/`) displays the current log level
- Direct link to Gunicorn configuration
- After changing configuration, a link to server restart is displayed

## Migration from Old Configuration

If you previously used `GUNICORN_LOG_LEVEL` in `.env` or as an environment variable:

```bash
# Run migration
python manage.py migrate mgmt

# Set configuration in Admin GUI
# Or via management command:
python manage.py shell
>>> from mgmt.models import GunicornConfig
>>> config = GunicornConfig.get_config()
>>> config.log_level = 'info'  # or 'debug', 'warning', etc.
>>> config.save()
```

After that, you can remove `GUNICORN_LOG_LEVEL` from `.env` and control everything via the Admin GUI.
