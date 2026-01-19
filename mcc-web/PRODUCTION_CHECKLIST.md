# Production Deployment Checklist

This checklist ensures that all important aspects for a professional production system are covered.

## Pre-Deployment

### 1. Code & Dependencies
- [ ] All changes committed and tested
- [ ] `requirements.txt` is up to date
- [ ] Pre-deployment checks executed: `python utils/pre_deployment_check.py`
- [ ] No debug output or test code in production

### 2. Environment Configuration
- [ ] `.env` file created for production (or system environment variables)
- [ ] `SECRET_KEY` set and secure (not the default value!)
- [ ] `DEBUG=False` in production
- [ ] `ALLOWED_HOSTS` correctly configured (not `*`)
- [ ] `CSRF_TRUSTED_ORIGINS` configured with HTTPS URLs
- [ ] `SESSION_COOKIE_SECURE=True` (for HTTPS)
- [ ] `CSRF_COOKIE_SECURE=True` (for HTTPS)

### 3. Database
- [ ] Migrations reset/consolidated (if necessary)
- [ ] Data migrations re-added (if necessary)
- [ ] Backup strategy defined
- [ ] Database backup created before deployment

### 4. Static & Media Files
- [ ] `STATIC_ROOT` correctly configured
- [ ] `MEDIA_ROOT` correctly configured
- [ ] Directories exist and have correct permissions
- [ ] Apache/Web server configured for static/media files

## Deployment

### 5. Deployment Process
- [ ] Deployment archive created: `python utils/create_deployment_archive.py`
- [ ] Archive transferred to production server
- [ ] Archive extracted on production server
- [ ] Virtual environment activated
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Deployment script executed: `python utils/deploy_production.py`
- [ ] Pre-deployment checks on production server: `python utils/pre_deployment_check.py`

### 6. Application Server
- [ ] Gunicorn configured (`gunicorn_config.py`)
- [ ] Systemd service created (`systemd/mcc-web.service`)
- [ ] Service enabled: `sudo systemctl enable mcc-web`
- [ ] Service started: `sudo systemctl start mcc-web`
- [ ] Service status checked: `sudo systemctl status mcc-web`

### 7. Web Server (Apache/Nginx)
- [ ] Reverse proxy configured
- [ ] SSL/TLS certificate installed
- [ ] `X-Forwarded-Proto` header set
- [ ] Static files served (not by Django)
- [ ] Media files served (not by Django)
- [ ] Health check endpoint reachable: `/health/`

## Post-Deployment

### 8. Verification
- [ ] Health check works: `curl http://your-domain/health/`
- [ ] Admin interface reachable
- [ ] API endpoints working
- [ ] Static files served correctly
- [ ] Media files served correctly
- [ ] Translations working (DE/EN)
- [ ] No errors in logs

### 9. Monitoring & Logging
- [ ] Logging configured (File or Syslog)
- [ ] Log rotation set up
- [ ] Monitoring tools configured (optional)
- [ ] Health check endpoint monitored

### 10. Backup & Maintenance
- [ ] Automatic database backups set up (Cron)
- [ ] Backup rotation configured
- [ ] Media files backup strategy defined
- [ ] Backup restoration tested

## Security

### 11. Security Settings
- [ ] `SECRET_KEY` securely stored (not in Git)
- [ ] `DEBUG=False` in production
- [ ] `ALLOWED_HOSTS` restrictively configured
- [ ] HTTPS enforced
- [ ] Security headers set (HSTS, CSP, etc.)
- [ ] Admin interface protected (strong password)
- [ ] API keys securely managed

### 12. File Permissions
- [ ] Database file: Readable/writable for web server user
- [ ] Media directory: Writable for web server user
- [ ] Static directory: Readable for web server user
- [ ] No sensitive files publicly accessible

## Automation

### 13. Automated Tasks
- [ ] Cron job for database backups: `utils/backup_database.py`
- [ ] Log rotation configured
- [ ] Automatic service restarts on errors (systemd)

## Documentation

### 14. Documentation
- [ ] Deployment process documented
- [ ] Rollback procedure documented
- [ ] Backup restoration documented
- [ ] Support contact information documented

## Emergency Procedures

### 15. Rollback Plan
- [ ] Rollback procedure defined
- [ ] Backup restoration tested
- [ ] Emergency contacts documented

## Files Created

The following files were created for the professional setup:

1. **`gunicorn_config.py`** - Gunicorn configuration
2. **`systemd/mcc-web.service`** - Systemd service file
3. **`utils/backup_database.py`** - Automatic backup script
4. **`utils/pre_deployment_check.py`** - Pre-deployment validation
5. **Health Check Endpoint** - `/health/` in `config/views.py`

## Quick Commands

```bash
# Pre-Deployment Checks
python utils/pre_deployment_check.py

# Create Backup
python utils/backup_database.py

# Deploy
python utils/deploy_production.py

# Check Health
curl http://your-domain/health/

# Systemd Service
sudo systemctl status mcc-web
sudo systemctl restart mcc-web
```

## Cron Job Example

Add to `/etc/crontab` for daily backups:

```cron
# Daily database backup at 2 AM
0 2 * * * www-data cd /data/games/mcc/mcc-web && /data/games/mcc/mcc-web/venv/bin/python utils/backup_database.py --keep-days 7 --compress
```

## Log Rotation

Create `/etc/logrotate.d/mcc-web`:

```
/data/games/mcc/mcc-web/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload mcc-web > /dev/null 2>&1 || true
    endscript
}
```

## Notes

- All scripts should be executed with the web server user (e.g., `www-data`)
- Backups should be tested regularly
- Health check should be monitored by monitoring tools
- Logs should be reviewed regularly
