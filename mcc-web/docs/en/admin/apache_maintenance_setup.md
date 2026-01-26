# Apache Maintenance Mode Setup

## Overview

This document describes how to activate the maintenance page (`maintenance.html`) in the PROD environment to display a professional maintenance page during maintenance work.

## Files

- **Maintenance HTML**: `project_static/maintenance.html`
- **Apache Config**: `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf` (or similar)

## Implementation Options

### Option 1: Apache ErrorDocument (Recommended)

The simplest method is to configure Apache to display the maintenance page when an error occurs (e.g., when Gunicorn is not reachable).

#### Step 1: Copy Maintenance File

```bash
# On PROD server
sudo cp /data/games/mcc/mcc-web/project_static/maintenance.html /var/www/maintenance.html
sudo chown www-data:www-data /var/www/maintenance.html
sudo chmod 644 /var/www/maintenance.html
```

#### Step 2: Adjust Apache Configuration

In the Apache VirtualHost configuration (e.g., `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf`), add **BEFORE** the ProxyPass rules:

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    ServerAdmin <YOUR ADMIN CONTACT>
    DocumentRoot /var/www/

    # ... (existing configuration) ...

    # Maintenance Mode: If Gunicorn is not reachable, show maintenance page
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
    ProxyPass /robots.txt !
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

#### Step 3: Reload Apache

```bash
sudo apache2ctl configtest  # Check configuration
sudo systemctl reload apache2
```

**Advantages:**
- Automatically active when Gunicorn is not reachable
- No manual activation required
- Works even with unexpected outages

---

### Option 2: Manual Maintenance Mode with RewriteRule

For planned maintenance work, a manual maintenance mode can be set up.

#### Step 1: Create Maintenance Flag File

**Note:** The maintenance flag file can now also be controlled via the Admin GUI (see "Mgmt" → "Maintenance Control").

**Manually (via command line):**

```bash
# Activate maintenance
sudo touch /data/var/mcc/apache/.maintenance_mode
sudo chmod 644 /data/var/mcc/apache/.maintenance_mode

# Deactivate maintenance
sudo rm /data/var/mcc/apache/.maintenance_mode
```

**Via Admin GUI (recommended):**

1. Navigate to **Mgmt** → **Maintenance Control**
2. Click **Activate Maintenance Mode** or **Deactivate Maintenance Mode**
3. Confirm the action

#### Step 2: Adjust Apache Configuration

In the Apache VirtualHost configuration **BEFORE** the ProxyPass rules:

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    # ... (existing configuration) ...

    # Maintenance Mode: Check for flag file
    RewriteEngine On
    
    # If maintenance flag exists AND not requesting /maintenance.html or /static/
    RewriteCond /data/var/mcc/apache/.maintenance_mode -f
    RewriteCond %{REQUEST_URI} !^/maintenance\.html$
    RewriteCond %{REQUEST_URI} !^/static/
    RewriteRule ^(.*)$ /maintenance.html [R=503,L]

    # Serve maintenance file directly
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
    ProxyPass /robots.txt !
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

**Note:** For RewriteRule, the `rewrite` module must be enabled:
```bash
sudo a2enmod rewrite
```

#### Step 3: Reload Apache

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

**Advantages:**
- Manual control over maintenance times
- Can be activated before planned maintenance
- Static files remain accessible (optionally configurable)

**Disadvantages:**
- Must be manually activated/deactivated
- Forgotten deactivation blocks the entire website

---

### Option 3: Combined (Automatic + Manual)

Combination of both methods for maximum flexibility:

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    # ... (existing configuration) ...

    RewriteEngine On
    
    # Manual maintenance mode (has priority)
    RewriteCond /data/var/mcc/apache/.maintenance_mode -f
    RewriteCond %{REQUEST_URI} !^/maintenance\.html$
    RewriteCond %{REQUEST_URI} !^/static/
    RewriteRule ^(.*)$ /maintenance.html [R=503,L]

    # Automatic maintenance mode on proxy errors
    ErrorDocument 502 /maintenance.html
    ErrorDocument 503 /maintenance.html
    ErrorDocument 504 /maintenance.html

    # Serve maintenance file directly
    Alias /maintenance.html /var/www/maintenance.html
    <Directory /var/www/>
        <Files "maintenance.html">
            Require all granted
        </Files>
    </Directory>

    # ... (existing ProxyPass rules) ...
</VirtualHost>
```

---

## Usage

### Automatic Mode (Option 1)

- **Activation**: Automatically when Gunicorn is not reachable
- **Deactivation**: Automatically when Gunicorn is reachable again

### Manual Mode (Option 2)

**Start maintenance (Admin GUI - recommended):**
1. Navigate to **Mgmt** → **Maintenance Control**
2. Click **Activate Maintenance Mode**
3. Confirm the action

**Start maintenance (command line):**
```bash
sudo touch /data/var/mcc/apache/.maintenance_mode
sudo chmod 644 /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2
```

**End maintenance (Admin GUI - recommended):**
1. Navigate to **Mgmt** → **Maintenance Control**
2. Click **Deactivate Maintenance Mode**
3. Confirm the action

**End maintenance (command line):**
```bash
sudo rm /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2
```

**Check status:**
```bash
if [ -f /data/var/mcc/apache/.maintenance_mode ]; then
    echo "Maintenance Mode: ACTIVE"
else
    echo "Maintenance Mode: INACTIVE"
fi
```

---

## Advanced Configuration

### Allow Static Files During Maintenance

If CSS/JS/Images should remain accessible during maintenance:

```apache
# In RewriteRule: /static/ already excluded
RewriteCond %{REQUEST_URI} !^/static/
```

### Allow Admin Access During Maintenance

For emergencies, admin access can be allowed during maintenance:

```apache
# IP-based exception (replace YOUR_IP with admin IP)
RewriteCond %{REMOTE_ADDR} !^YOUR_IP$
RewriteCond /data/var/mcc/apache/.maintenance_mode -f
RewriteCond %{REQUEST_URI} !^/maintenance\.html$
RewriteCond %{REQUEST_URI} !^/static/
RewriteRule ^(.*)$ /maintenance.html [R=503,L]
```

### Custom HTTP Status Code

By default, `503 Service Unavailable` is used. This signals to search engines that the maintenance is temporary.

---

## Testing

### Test 1: Automatic Mode

```bash
# Stop Gunicorn
sudo systemctl stop mcc-web  # or corresponding

# Call website - should show maintenance page
curl -I https://mycyclingcity.net/
# Expected: HTTP/1.1 502 Bad Gateway or 503 Service Unavailable

# Start Gunicorn
sudo systemctl start mcc-web

# Call website - should work normally
curl -I https://mycyclingcity.net/
# Expected: HTTP/1.1 200 OK
```

### Test 2: Manual Mode

```bash
# Activate maintenance (via Admin GUI or command line)
sudo touch /data/var/mcc/apache/.maintenance_mode
sudo chmod 644 /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2

# Call website
curl -I https://mycyclingcity.net/
# Expected: HTTP/1.1 503 Service Unavailable

# Deactivate maintenance (via Admin GUI or command line)
sudo rm /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2

# Call website
curl -I https://mycyclingcity.net/
# Expected: HTTP/1.1 200 OK
```

---

## Recommendation

**For PROD environment recommended: Option 1 (Automatic) or Option 3 (Combined)**

- **Option 1**: Simple, automatic, no manual intervention needed
- **Option 3**: Maximum flexibility, automatic on outages, manual for planned maintenance

---

## Important Notes

1. **Backup**: Always create a backup before making changes to Apache configuration
2. **Test**: Test changes first in a test environment
3. **Monitoring**: Monitor logs during maintenance work
4. **Communication**: Inform users about planned maintenance (e.g., via email, social media)

---

## Troubleshooting

### Maintenance Page Not Displayed

1. Check if maintenance flag exists: `ls -la /data/var/mcc/apache/.maintenance_mode`
2. Check if Apache can read the flag file: `sudo -u www-data test -f /data/var/mcc/apache/.maintenance_mode && echo "OK" || echo "ERROR"`
3. Check if maintenance HTML exists: `ls -la /var/www/maintenance.html`
4. Check if Apache can read the HTML file: `sudo -u www-data cat /var/www/maintenance.html`
5. Check if Alias is correct: `apache2ctl -S`
6. Check Apache error log: `sudo tail -f /var/log/apache2/MCC_ssl_error_log.*`

### Apache Won't Start After Changes

1. Check configuration: `sudo apache2ctl configtest`
2. Fix syntax errors
3. Module enabled? `sudo a2enmod rewrite` (if using RewriteRule)

### Static Files Blocked

- In RewriteRule ensure `/static/` is excluded
- Check if `ProxyPass /static/ !` is correctly set
