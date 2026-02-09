# Maintenance Mode Setup

## Overview

This document describes how the Maintenance Mode works in the PROD environment. The Maintenance Mode is controlled by **Django Middleware** and provides advanced features such as IP whitelist and admin access.

## Architecture

### Django Middleware (Main Control)

The **Django Middleware** (`mgmt.middleware_maintenance.MaintenanceModeMiddleware`) takes full control of the Maintenance Mode:

- ✅ Checks the maintenance flag file
- ✅ Supports IP whitelist (single IPs and CIDR blocks)
- ✅ Allows admin access for superusers
- ✅ Blocks all other requests and redirects to maintenance page

### Apache ErrorDocument (Fallback)

Apache automatically displays the maintenance page when Gunicorn is not reachable (502/503/504 errors). This is a **fallback mechanism** for unexpected outages.

## Files

- **Maintenance HTML**: `project_static/maintenance.html` (with login button)
- **Flag File**: `/data/var/mcc/apache/.maintenance_mode`
- **Apache Config**: `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf`

## Apache Configuration

### Step 1: Copy Maintenance File

```bash
# On PROD server
sudo cp /data/appl/mcc/mcc-web/project_static/maintenance.html /var/www/maintenance.html
sudo chown www-data:www-data /var/www/maintenance.html
sudo chmod 644 /var/www/maintenance.html
```

### Step 2: Adjust Apache Configuration

In the Apache VirtualHost configuration (e.g., `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf`):

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    ServerAdmin <YOUR ADMIN CONTACT>
    DocumentRoot /var/www/

    # ... (existing configuration) ...

    # Maintenance Mode: Only for Gunicorn outages (fallback)
    # Django Middleware takes main control
    ErrorDocument 502 /maintenance.html
    ErrorDocument 503 /maintenance.html
    ErrorDocument 504 /maintenance.html

    # Serve maintenance file directly (without proxy)
    Alias /maintenance.html /var/www/maintenance.html
    <Directory /var/www/>
        <Files "maintenance.html">
            Require all granted
        </Files>
    </Directory>

    # ... (existing ProxyPass rules) ...
    ProxyPreserveHost On
    ProxyPass /maintenance.html !
    ProxyPass /static/ !
    ProxyPass /media/ !
    ProxyPass /robots.txt !
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

### Step 3: Reload Apache

```bash
sudo apache2ctl configtest  # Check configuration
sudo systemctl reload apache2
```

## Usage

### Activate/Deactivate Maintenance Mode

**Via Admin GUI (recommended):**

1. Navigate to **Mgmt** → **Maintenance Control**
2. Click **Activate Maintenance Mode** or **Deactivate Maintenance Mode**
3. Confirm the action

**Manually (via command line):**

```bash
# Activate maintenance
touch /data/var/mcc/apache/.maintenance_mode
chmod 644 /data/var/mcc/apache/.maintenance_mode

# Deactivate maintenance
rm /data/var/mcc/apache/.maintenance_mode
```

**Check status:**

```bash
if [ -f /data/var/mcc/apache/.maintenance_mode ]; then
    echo "Maintenance Mode: ACTIVE"
else
    echo "Maintenance Mode: INACTIVE"
fi
```

## IP Whitelist Configuration

### Via Admin GUI

1. Navigate to **Mgmt** → **Maintenance Configurations**
2. Add IP addresses or CIDR blocks (one per line):
   ```
   192.168.1.100
   10.0.0.0/8
   172.16.0.0/12
   ```
3. Enable "Allow admin access during maintenance" (if desired)
4. Save the configuration

### Supported Formats

- **Single IP**: `192.168.1.100`
- **CIDR Block**: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.1.0/24`

## Behavior During Maintenance Mode

### Allowed Access

- ✅ **Static files** (`/static/`) - Always accessible
- ✅ **Media files** (`/media/`) - Always accessible
- ✅ **Maintenance page** (`/maintenance.html`) - Always accessible
- ✅ **Admin area** (`/admin/`, `/de/admin/`) - Always accessible (for login)
- ✅ **IP Whitelist** - All pages accessible if IP is in whitelist
- ✅ **Superuser** - All pages accessible (if `allow_admin_during_maintenance=True`)

### Blocked Access

- ❌ All other pages (redirected to maintenance page)

## Logs

### Django Middleware Logs

Middleware logs are written to `/data/var/mcc/logs/mgmt.log`:

```bash
# Show middleware logs in real-time
tail -f /data/var/mcc/logs/mgmt.log | grep MaintenanceMode

# Example logs:
# INFO [MaintenanceMode] Redirecting IP 141.15.25.200 to maintenance page (path: /de/map/)
# DEBUG [MaintenanceMode] Allowing admin access (path: /admin/)
# DEBUG [MaintenanceMode] Allowing access for superuser admin from IP 84.132.227.73 (path: /de/map/)
```

### Log Levels

- **INFO**: Requests are redirected to maintenance page
- **DEBUG**: Admin access or IP whitelist allows access
- **WARNING**: Configuration errors (fallback behavior)
- **ERROR**: Critical errors

## Testing

### Test 1: Activate Maintenance Mode

```bash
# Activate maintenance (via Admin GUI or command line)
touch /data/var/mcc/apache/.maintenance_mode
chmod 644 /data/var/mcc/apache/.maintenance_mode

# Call website - should show maintenance page
curl -I https://mycyclingcity.net/de/map/
# Expected: HTTP/1.1 302 Found (Redirect to /maintenance.html)

# Test admin access
curl -I https://mycyclingcity.net/admin/
# Expected: HTTP/1.1 200 OK (Login page accessible)
```

### Test 2: IP Whitelist

```bash
# Add IP to whitelist (via Admin GUI)
# Then test from this IP:
curl -I https://mycyclingcity.net/de/map/
# Expected: HTTP/1.1 200 OK (Access allowed)
```

### Test 3: Superuser Access

```bash
# Login as superuser
# Then test:
curl -I -H "Cookie: sessionid=..." https://mycyclingcity.net/de/map/
# Expected: HTTP/1.1 200 OK (Access allowed)
```

### Test 4: Gunicorn Outage (Apache Fallback)

```bash
# Stop Gunicorn
sudo systemctl stop mcc-web  # or corresponding

# Call website - should show maintenance page (via Apache ErrorDocument)
curl -I https://mycyclingcity.net/
# Expected: HTTP/1.1 502 Bad Gateway or 503 Service Unavailable

# Start Gunicorn
sudo systemctl start mcc-web

# Call website - should work normally
curl -I https://mycyclingcity.net/
# Expected: HTTP/1.1 200 OK
```

## Troubleshooting

### Maintenance Page Not Displayed

1. **Check if flag file exists:**
   ```bash
   ls -la /data/var/mcc/apache/.maintenance_mode
   ```

2. **Check if Django Middleware is active:**
   ```bash
   # In settings.py should be:
   # 'mgmt.middleware_maintenance.MaintenanceModeMiddleware'
   grep -r "MaintenanceModeMiddleware" /data/appl/mcc/mcc-web/config/settings.py
   ```

3. **Check if Apache RewriteRule intercepts requests:**
   ```bash
   # Should NOT have RewriteRule for .maintenance_mode
   grep -r "maintenance_mode\|RewriteCond.*maintenance" /etc/apache2/sites-available/
   ```

4. **Check Django logs:**
   ```bash
   tail -50 /data/var/mcc/logs/mgmt.log | grep MaintenanceMode
   ```

### Admin Access Not Working

1. **Check if `/admin/` is accessible:**
   ```bash
   curl -I https://mycyclingcity.net/admin/
   # Should: HTTP/1.1 200 OK (not 302 Redirect)
   ```

2. **Check if `allow_admin_during_maintenance=True`:**
   - Admin GUI → **Mgmt** → **Maintenance Configurations**
   - Check "Allow admin access during maintenance"

3. **Check if user is superuser:**
   - Admin GUI → **Authentication and Authorization** → **Users**
   - Check "Superuser status"

### IP Whitelist Not Working

1. **Check if IP is entered correctly:**
   - One IP per line
   - No spaces
   - Correct format (e.g., `192.168.1.100` or `10.0.0.0/8`)

2. **Check if client IP is detected correctly:**
   ```bash
   # Client IP should appear in logs
   tail -f /data/var/mcc/logs/mgmt.log | grep MaintenanceMode
   ```

3. **With Proxy/Load Balancer:**
   - IP is read from `X-Forwarded-For` header
   - Check if Apache forwards the header correctly

### Django Logs Show No Entries

1. **Check if requests reach Django:**
   ```bash
   # If Apache RewriteRule is active, requests don't reach Django
   # Remove all RewriteRule configurations for maintenance
   ```

2. **Check if log level is correct:**
   - Middleware uses `logger.info()` and `logger.debug()`
   - Log level should be at least `INFO`

## Important Notes

1. **Disable Apache RewriteRule**: Apache should **NOT** use RewriteRule for the maintenance flag file, as this blocks the Django Middleware.

2. **IP Whitelist**: The IP whitelist only works if Django has control. If Apache intercepts requests, the IP whitelist won't work.

3. **Admin Access**: Superusers can access all pages if `allow_admin_during_maintenance=True` is enabled.

4. **Maintenance Page**: The maintenance page (`/maintenance.html`) has a login button so admins can log in.

5. **Logs**: All middleware activities are logged to `/data/var/mcc/logs/mgmt.log`.

## Recommendation

**For PROD environment:**

- ✅ **Django Middleware** for planned maintenance (with IP whitelist and admin access)
- ✅ **Apache ErrorDocument** as fallback for unexpected Gunicorn outages
- ❌ **NO Apache RewriteRule** for maintenance flag file

This configuration provides maximum flexibility and functionality.
