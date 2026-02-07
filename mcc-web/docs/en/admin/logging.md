# View Log Files in Admin GUI

## Overview

Logs are stored in files and can be viewed via the Log File Viewer in the Admin GUI.

## Log Files

Logs are stored in the following files:
- `data/logs/api.log` - API application (development) / `/data/var/mcc/logs/api.log` (production)
- `data/logs/mgmt.log` - Management application (development) / `/data/var/mcc/logs/mgmt.log` (production)
- `data/logs/iot.log` - IoT application (development) / `/data/var/mcc/logs/iot.log` (production)
- `data/logs/kiosk.log` - Kiosk application (development) / `/data/var/mcc/logs/kiosk.log` (production)
- `data/logs/game.log` - Game application (development) / `/data/var/mcc/logs/game.log` (production)
- `data/logs/django.log` - Django framework (WARNING+ only) (development) / `/data/var/mcc/logs/django.log` (production)
- `data/logs/gunicorn_access.log` - Gunicorn access logs (development) / `/data/var/mcc/logs/gunicorn_access.log` (production)
- `data/logs/gunicorn_error.log` - Gunicorn error logs (development) / `/data/var/mcc/logs/gunicorn_error.log` (production)

## View Logs in Admin

1. **Open Admin GUI**: `/admin/`
2. **Navigation**: "Mgmt" → "View Application Logs"
3. **Direct URL**: `/admin/logs/`
4. **Select Log File**: Choose a log file from the dropdown menu
5. **Features**:
   - Real-time log display
   - Auto-refresh function
   - Search in log entries
   - Browse rotated log files

## Log Levels

All log levels are stored in log files:
- **DEBUG** - Debug information
- **INFO** - Information messages
- **WARNING** - Warnings
- **ERROR** - Errors
- **CRITICAL** - Critical errors

Log levels can be configured per app in `config/settings.py`.

## View Log Files

### In Terminal:
```bash
# API logs (development)
tail -f data/logs/api.log

# Management logs (development)
tail -f data/logs/mgmt.log

# All app logs simultaneously (development)
tail -f data/logs/*.log
```

### In Admin GUI:
- **Management** → **View Application Logs**
- Select the desired log file
- Filterable by level, date, etc.

## Best Practices

1. **Log Rotation**: Automatic rotation at 50 MB per file (10 backups)
2. **Monitoring**: Regularly check critical logs
3. **Retention**: Old log files are automatically rotated
4. **Performance**: Logs are written directly to files, no database overhead
