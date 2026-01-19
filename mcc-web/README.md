# MyCyclingCity - Web Application

Django-based web application for the MyCyclingCity cycling infrastructure tracking system.

## Setup and Installation

### Creating Deployment Archive

In the development directory:

```bash
cd mcc-web
python utils/create_deployment_archive.py
```

### Target System Preparation and Installation

```bash
mkdir -p /data/games/mcc/mcc-web
cd /data/games/mcc/mcc-web
```

#### Python Environment Setup

Initialize Python virtual environment in project directory:

```bash
python3 -m venv venv
source venv/bin/activate
```

**Note**: For development, you can use an external virtual environment if working from different systems with different Python installations on a NAS server (e.g., `~/venv_mcc`). Use the corresponding path to activate it.

#### Extract Archive

```bash
tar xvf /tmp/mcc-web-deployment-<VERSION>-<DATE>_<TIME>.tar.gz
```

#### Install Python Dependencies

```bash
pip install -r requirements.txt
```

Required packages (from requirements.txt):
- Django==5.2.9
- requests==2.32.5
- gunicorn==23.0.0
- gpxpy==1.6.2
- pillow==12.0.0
- python-decouple==3.8
- python-dotenv==1.0.0
- pytest==8.0.0
- pytest-django==4.8.0
- factory-boy==3.3.0
- qrcode[pil]==7.4.2

#### Deploy to Production

```bash
python utils/deploy_production.py
```

#### Create Admin User

```bash
python manage.py createsuperuser
python manage.py changepassword <ADMIN_USER>
```

## Running the Server

### Development Server

```bash
python manage.py runserver
```

Access the application:
- Admin: http://127.0.0.1:8000/admin
- Game: http://127.0.0.1:8000/game/
- Map: http://127.0.0.1:8000/map/

### Production Server with Gunicorn

On the production server, we use Apache as a reverse proxy and Gunicorn as the Python application server.

#### Collect Static Files

All static files must be collected into the directory defined by `STATIC_ROOT`:

```bash
python manage.py collectstatic
```

The files in this directory are served by the Apache web server to separate static content from dynamically generated content.

#### Start Gunicorn

```bash
gunicorn --workers 5 --threads 2 --bind 127.0.0.1:8001 config.wsgi:application --log-level info
```

**Security Note**: Gunicorn is bound to `127.0.0.1` (localhost only) instead of `0.0.0.0` for security. This ensures that Gunicorn is only accessible from the local machine through the Apache reverse proxy. External access is only possible through Apache, which handles SSL/TLS termination and authentication.

Access the application:
- **Via Apache (Production)**: Use the configured domain (e.g., `https://mycyclingcity.net`)
- **Direct (Development/Testing)**: `http://127.0.0.1:8001/admin` (only accessible from localhost)

## API Endpoints

The web application provides various API endpoints for device communication and data access. For a complete overview, see `URLS_OVERVIEW.md`.

### Main API Endpoints (under `/api/`)

#### Data Transmission
- `POST /api/update-data` - Receive tachometer data from devices
- `POST /api/get-user-id` - Retrieve username for RFID tag

#### Cyclist & Group Data
- `GET /api/get-cyclist-coins/<username>` - Get cyclist coins
- `POST /api/spend-cyclist-coins` - Spend cyclist coins
- `GET /api/get-cyclist-distance/<identifier>` - Get cyclist distance
- `GET /api/get-group-distance/<identifier>` - Get group distance
- `GET /api/get-active-cyclists` - List active cyclists
- `GET /api/list-cyclists` - List all cyclists
- `GET /api/list-groups` - List all groups

#### Leaderboards
- `GET /api/get-leaderboard/cyclists` - Cyclist leaderboard
- `GET /api/get-leaderboard/groups` - Group leaderboard

#### Milestones & Rewards
- `GET /api/get-milestones` - Get milestones
- `GET /api/get-statistics` - Get statistics
- `GET /api/get-travel-locations` - Get travel locations
- `GET /api/get-group-rewards` - Get group rewards
- `POST /api/redeem-milestone-reward` - Redeem milestone reward

#### Device Management
- `POST /api/device/config/report` - Device reports its configuration
- `GET /api/device/config/fetch` - Device fetches server-side configuration
- `GET /api/device/firmware/info` - Check for firmware updates
- `GET /api/device/firmware/download` - Download firmware binary
- `POST /api/device/heartbeat` - Device heartbeat signal

#### Kiosk Management
- `GET /api/kiosk/<uid>/playlist` - Get kiosk playlist
- `GET /api/kiosk/<uid>/commands` - Get kiosk commands

**Note**: Most endpoints require authentication via `X-Api-Key` header (device-specific or global API key).

## Simulating Devices

In the `test` directory, you can use `mcc_api_test.py` to simulate sending kilometer data.

First, adjust the port in `mcc_api_test.cfg` to 8000 (runserver) or 8001 (gunicorn).

```bash
python3 test/mcc_api_test.py --id_tag "rfid001" --device "mcc-test-01" --distance "0.1" --interval 5 --loop
```

## Cron Job for Active Sessions

If no kilometer data is sent from a device, the current session is not automatically ended and written to history.

### MCC Worker - Saves Active Sessions to History Every 5 Minutes

```cron
*/5 * * * * cd /data/games/mcc/mcc-web && /data/games/mcc/mcc-web/venv/bin/python manage.py mcc_worker >> /data/games/mcc/mcc-web/logs/mcc_worker.log 2>&1
```

## Apache Configuration

### Set Permissions

Set permissions so the Apache web server user `www-data` can access static files:

```bash
chgrp www-data /data /data/games /data/games/mcc /data/games/mcc/mcc-web
chgrp -R www-data /data/games/mcc/mcc-web/staticfiles
```

### Apache Virtual Host Configuration

Configure `/etc/apache2/sites-enabled/mcc.conf`:

#### HTTP to HTTPS Redirect

```apache
<VirtualHost mycyclingcity.net:80>
    ServerName mycyclingcity.net
    ServerAdmin <YOUR ADMIN CONTACT>
    DocumentRoot /var/www/

    LogLevel info
    ErrorLog  "|/usr/bin/rotatelogs -l ${APACHE_LOG_DIR}/MCC_error_log.%Y%m%d 86400"
    CustomLog "|/usr/bin/rotatelogs -l ${APACHE_LOG_DIR}/MCC_access_log.%Y%m%d 86400" common

    RewriteEngine On
    RewriteCond %{HTTPS} !=on
    RewriteRule ^/?(.*) https://%{SERVER_NAME}/$1 [R,L]

    RewriteCond %{SERVER_NAME} =mycyclingcity.net
    RewriteRule ^ https://%{SERVER_NAME}%{REQUEST_URI} [END,NE,R=permanent]
</VirtualHost>
```

#### HTTPS Virtual Host

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    ServerAdmin <YOUR ADMIN CONTACT>
    DocumentRoot /var/www/

    LogLevel info
    ErrorLog  "|/usr/bin/rotatelogs -l ${APACHE_LOG_DIR}/MCC_ssl_error_log.%Y%m%d 86400"
    LogFormat "%h %l %u %t %{SSL_PROTOCOL}x %{SSL_CIPHER}x \"%r\" %>s %b" mccssl
    CustomLog "|/usr/bin/rotatelogs -l ${APACHE_LOG_DIR}/MCC_ssl_access_log.%Y%m%d 86400" mccssl

    # Inform Django that the original request was HTTPS (very important!)
    RequestHeader set X-Forwarded-Proto "https"

    # Inform Django about the original hostname
    RequestHeader set X-Forwarded-Host "mycyclingcity.net"

    Alias /robots.txt /data/games/mcc/mcc-web/staticfiles/robots.txt

    # Add static files (CSS, JS, images)
    # These must have been collected with 'python manage.py collectstatic'
    # and be in the path specified here
    Alias /static /data/games/mcc/mcc-web/staticfiles/

    <Directory /data/games/mcc/mcc-web/staticfiles/>
        Require all granted
    </Directory>

    # Root redirect (ensures trailing slash)
    RedirectMatch permanent ^/$ https://mycyclingcity.net/de/map/

    # Proxy rules (IMPORTANT: order and slashes)
    # Everything that is NOT /static/ or /robots.txt goes to Django
    ProxyPreserveHost On
    ProxyPass /static/ !
    ProxyPass /robots.txt !
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/

    SSLCertificateFile /etc/letsencrypt/live/mycyclingcity.net/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/mycyclingcity.net/privkey.pem
    Include /etc/letsencrypt/options-ssl-apache.conf
</VirtualHost>
```

## Kiosk System Setup on Raspberry Pi 5

```bash
apt install xserver-xorg x11-xserver-utils xinit openbox chromium unclutter labwc seatd polkitd xdg-desktop-portal -y
```

### Kiosk User Setup

- Start script for kiosk user `mccadm`: `/home/mccadm/start-kiosk.sh` (TODO)
- Make script executable and set owner/group (TODO)
- Systemd service configuration: `/etc/systemd/system/mcc-kiosk.service` (TODO)

## Administrative Scripts

Administrative shell scripts are located in the `scripts/` directory:

- `check_test_status.sh` - Check if extended cronjob test is running
- `monitor_test.sh` - Continuous monitoring for extended cronjob test
- `monitor_test_continuous.sh` - Detailed monitoring for 30-minute extended cronjob test
- `monitor_30min_test.sh` - Basic monitoring for 30-minute extended cronjob test

These scripts are utility tools for monitoring test processes and do not require Django's `manage.py`. They can be executed directly from the `scripts/` directory.

## Load Testing

In the `test` directory, there is a Python script with configuration data to simulate devices and cyclists.

The `mcc_api_test.py` script supports various modes and parameters for realistic load testing.

### Basic Usage

1. Single test call:
   ```bash
   python3 test/mcc_api_test.py --id_tag "rfid001" --device "mcc-demo01" --distance 0.1
   ```

2. Continuous test with fixed distance:
   ```bash
   python3 test/mcc_api_test.py --id_tag "rfid001" --device "mcc-demo01" --distance 0.1 --loop
   ```

3. Continuous test with simulated distance:
   ```bash
   python3 test/mcc_api_test.py --id_tag "rfid001" --device "mcc-demo01" --loop
   ```

### Automated Load Testing with Test Data File

4. Basic call with test data file (all devices in parallel):
   ```bash
   python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json
   ```

5. Limited number of devices:
   ```bash
   python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --max-devices 5
   ```

6. Limited concurrent connections:
   ```bash
   python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --max-concurrent 3
   ```

7. Combined: 10 devices, max 5 concurrent connections:
   ```bash
   python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --max-devices 10 --max-concurrent 5
   ```

### Realistic Simulation

8. With time jitter for more realistic load distribution:
   ```bash
   python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --send-jitter 1.0
   ```

9. With retry mechanism on errors (like real devices):
   ```bash
   python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --retry-attempts 5 --retry-delay 2.0
   ```

10. With cyclist duration (60 seconds, then switch):
    ```bash
    python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --cyclist-duration 60
    ```

11. Fully configured load test:
    ```bash
    python3 test/mcc_api_test.py --loop \
        --test-data-file test/test_data_example.json \
        --max-devices 20 \
        --max-concurrent 5 \
        --send-jitter 0.8 \
        --retry-attempts 4 \
        --retry-delay 1.5 \
        --cyclist-duration 60 \
        --interval 10
    ```

### Speed Simulation

12. With wheel size (automatic speed calculation):
    ```bash
    python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --wheel-size 26
    ```

13. With fixed speed:
    ```bash
    python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --speed 15.0
    ```

14. With wheel size and fixed speed:
    ```bash
    python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --wheel-size 28 --speed 20.0
    ```

### Production Server (with DNS)

15. Test against production server:
    ```bash
    python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --dns
    ```

16. With adjusted interval:
    ```bash
    python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --interval 5
    ```

### Additional Functions

17. Query user ID:
    ```bash
    python3 test/mcc_api_test.py --get-user-id --id_tag "rfid001"
    ```

18. With custom configuration file:
    ```bash
    python3 test/mcc_api_test.py --loop --test-data-file test/test_data_example.json --config test/custom_config.cfg
    ```

### Parameter Overview

- `--id_tag`: Cyclist ID tag
- `--device`: Device ID
- `--distance`: Distance in kilometers
- `--interval`: Send interval in seconds
- `--loop`: Continuous mode
- `--test-data-file`: JSON file with devices and ID tags
- `--max-devices`: Maximum number of devices to use
- `--max-concurrent`: Maximum concurrent connections
- `--send-jitter`: Time jitter for send pulses (default: 0.5s)
- `--retry-attempts`: Number of retry attempts (default: 3)
- `--retry-delay`: Base delay for retries (default: 1.0s)
- `--cyclist-duration`: Cyclist duration on device (default: 60s)
- `--wheel-size`: Wheel size (20, 24, 26, 28 inches)
- `--speed`: Fixed speed in km/h
- `--dns`: Uses DNS URL and Authorization header
- `--config`: Path to configuration file

