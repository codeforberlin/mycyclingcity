# Production Logging Setup - Best Practices

## Overview

The logging system is configured according to **Production Best Practices**:

- ✅ **App-specific log files**: Each application writes to its own file
- ✅ **Root logger at WARNING**: Only critical errors reach Gunicorn
- ✅ **No propagation**: App logs are NOT passed to Gunicorn
- ✅ **Separate Django logs**: Framework logs in separate file

## Log File Structure

```
logs/
├── api.log          # API application (api.views, api.models, etc.)
├── mgmt.log         # Management application (mgmt.admin, mgmt.views, etc.)
├── iot.log           # IoT application (iot.models, iot.views, etc.)
├── kiosk.log         # Kiosk application (kiosk.views, etc.)
├── game.log          # Game application (game.views, game.models, etc.)
├── django.log        # Django framework (WARNING+ only)
├── gunicorn_access.log  # Gunicorn access logs
└── gunicorn_error.log   # Gunicorn error logs (critical errors only)
```

## Configuration

### Root Logger
- **Level**: `WARNING` (not DEBUG!)
- **Handler**: Only `django_file` (Django framework logs)
- **Purpose**: Catches only critical Django framework errors

### App Loggers (api, mgmt, iot, kiosk, game)
- **Level**: `DEBUG` (can be changed to `INFO` for production)
- **Handler**: 
  - App-specific file (e.g., `api_file` → `api.log`)
- **Propagate**: `False` ⚠️ **CRITICAL**: Prevents logs from being passed to root logger/Gunicorn

**Note:** Logs are no longer stored in the database, only in files.

### Django Framework Logger
- **Level**: `WARNING`
- **Handler**: `django_file` → `django.log`
- **Propagate**: `False`

## Why This Configuration?

### 1. Separation of Concerns
Each application has its own log file, making debugging easier:
- API problems → `logs/api.log`
- Management problems → `logs/mgmt.log`
- etc.

### 2. Gunicorn is Not Overloaded
- `propagate=False` prevents app logs from being passed to root logger
- Root logger at `WARNING` → only critical errors reach Gunicorn
- `gunicorn_error.log` stays clean and contains only real server errors

### 3. Scalability
- Each app can be configured independently
- Log levels can be adjusted per app
- File rotation per app (50 MB, 10 backups)

## Adjust Log Levels

### For Production (fewer logs):
```python
'api': {
    'handlers': ['api_file'],
    'level': 'INFO',  # Instead of DEBUG
    'propagate': False,
},
```

### For Development (more logs):
```python
'api': {
    'handlers': ['api_file'],
    'level': 'DEBUG',  # All logs
    'propagate': False,
},
```

## View Logs

### In Terminal:
```bash
# API logs
tail -f logs/api.log

# Management logs
tail -f logs/mgmt.log

# All app logs simultaneously
tail -f logs/*.log
```

### In Admin GUI:
- **Management** → **Log File Viewer**
- Select the desired log file
- Filterable by level, date, etc.

## Best Practices

### Set Log Levels Correctly
- **DEBUG**: Only for detailed debugging
- **INFO**: Normal operations (recommended for production)
- **WARNING**: Potential problems
- **ERROR**: Errors that need to be fixed
- **CRITICAL**: Critical system errors

### Monitoring
- Regularly check `logs/django.log` for framework errors
- Regularly check `logs/gunicorn_error.log` for server errors
- Use the Admin GUI for critical app logs

### Log Rotation
- Automatic rotation at 50 MB per file
- 10 backups per app log file
- 5 backups for Django logs

## Troubleshooting

### Problem: No Logs in App Files
**Solution**: Check if `propagate=False` is set

### Problem: Too Many Logs in Gunicorn
**Solution**: Check if root logger is at `WARNING` and app loggers have `propagate=False`

### Problem: Logs Don't Appear
**Solution**: 
1. Check file permissions: `chmod 644 logs/*.log`
2. Check if logger levels are correct
3. Check if handlers are configured correctly
