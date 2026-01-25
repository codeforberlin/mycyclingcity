# Installation Guide - Neue Deployment-Struktur

Diese Anleitung beschreibt die Installation der mcc-web Anwendung mit der neuen Deployment-Struktur:
- Code in `/data/appl/mcc/`
- Variable Daten in `/data/var/mcc/`

## Voraussetzungen

- Python 3.11 oder höher
- Virtual Environment Support
- Apache (für Production)
- Root- oder sudo-Zugriff für Verzeichniserstellung

## Schritt 1: Verzeichnisse erstellen

```bash
# Als root oder mit sudo
mkdir -p /data/appl/mcc
mkdir -p /data/var/mcc/{db,media,staticfiles,logs,backups,locale_compiled,tmp}

# Berechtigungen setzen (anpassen je nach Benutzer-Konfiguration)
# Option 1: Gleicher Benutzer für alles (Entwicklung)
chown -R <benutzer>:<gruppe> /data/appl/mcc
chown -R <benutzer>:<gruppe> /data/var/mcc
chmod -R 755 /data/appl/mcc
chmod -R 755 /data/var/mcc

# Option 2: Getrennte Benutzer (Produktion)
# Installationsbenutzer (z.B. admin, deploy)
chown -R <install-user>:<install-group> /data/appl/mcc
chmod -R 755 /data/appl/mcc

# Laufzeitbenutzer (z.B. www-data, mcc-web)
chown -R <runtime-user>:<runtime-group> /data/var/mcc
chmod -R 775 /data/var/mcc
```

## Schritt 2: Tar-Archiv extrahieren

```bash
# Als Installationsbenutzer
cd /data/appl/mcc

# Tar-Archiv extrahieren (z.B. von GitHub Actions generiert)
tar -xzf mcc-web-deployment-1.0.0-20260124_135111.tar.gz

# Dies erstellt: /data/appl/mcc/mcc-web-1.0.0/
```

## Schritt 3: Symlink erstellen

```bash
# Als Installationsbenutzer
cd /data/appl/mcc
ln -sfn mcc-web-1.0.0 mcc-web
```

## Schritt 4: Virtual Environment erstellen

```bash
# Als Installationsbenutzer
cd /data/appl/mcc

# Virtual Environment erstellen
python3 -m venv venv

# Dependencies installieren
venv/bin/pip install --upgrade pip
venv/bin/pip install -r mcc-web-1.0.0/requirements.txt
```

## Schritt 5: .env Datei erstellen

```bash
# Als Installationsbenutzer
cd /data/appl/mcc

# .env Datei erstellen (aus Beispiel oder bestehender Konfiguration)
if [ -f mcc-web-1.0.0/.env.example ]; then
    cp mcc-web-1.0.0/.env.example .env
else
    # Erstelle .env manuell
    cat > .env << EOF
SECRET_KEY=django-insecure-YOUR_SECRET_KEY_HERE
DEBUG=False
ALLOWED_HOSTS=mycyclingcity.net,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://mycyclingcity.net
MCC_APP_API_KEY=YOUR_API_KEY_HERE
# ... weitere Konfiguration
EOF
fi

# Berechtigungen setzen
chmod 640 .env
# Optional: Gruppe für Lesezugriff
# chgrp <runtime-group> .env
```

## Schritt 6: Berechtigungen setzen

```bash
# Als Installationsbenutzer oder root
cd /data/appl/mcc

# Code-Verzeichnis
chown -R <install-user>:<install-group> mcc-web-1.0.0
chmod -R 755 mcc-web-1.0.0

# .env Datei
chown <install-user>:<install-group> .env
chmod 640 .env

# venv
chown -R <install-user>:<install-group> venv
chmod -R 755 venv

# Daten-Verzeichnis (falls getrennte Benutzer)
# chown -R <runtime-user>:<runtime-group> /data/var/mcc
# chmod -R 775 /data/var/mcc
```

## Schritt 7: Migrationen ausführen

```bash
# Als Installationsbenutzer oder Laufzeitbenutzer
cd /data/appl/mcc/mcc-web

# Umgebungsvariable setzen (optional)
export MCC_ENV=production

# Migrationen ausführen (nur CREATE-Operationen)
/data/appl/mcc/venv/bin/python manage.py migrate
```

## Schritt 8: Static Files sammeln

```bash
# Als Installationsbenutzer oder Laufzeitbenutzer
cd /data/appl/mcc/mcc-web

/data/appl/mcc/venv/bin/python manage.py collectstatic --noinput
```

## Schritt 9: Übersetzungen kompilieren

```bash
# Als Installationsbenutzer oder Laufzeitbenutzer
cd /data/appl/mcc/mcc-web

/data/appl/mcc/venv/bin/python manage.py compilemessages
```

## Schritt 10: Gunicorn starten

```bash
# Als Installationsbenutzer oder Laufzeitbenutzer
cd /data/appl/mcc/mcc-web

# Start-Script verwenden
./scripts/start_gunicorn.sh

# Oder manuell:
export DJANGO_SETTINGS_MODULE=config.settings
export PYTHONPATH=/data/appl/mcc/mcc-web
/data/appl/mcc/venv/bin/gunicorn -c config/gunicorn_config.py config.wsgi:application
```

## Schritt 11: Apache konfigurieren

Erstelle oder aktualisiere `/etc/apache2/sites-enabled/mcc.conf`:

```apache
# HTTP to HTTPS Redirect
<VirtualHost mycyclingcity.net:80>
    ServerName mycyclingcity.net
    Redirect permanent / https://mycyclingcity.net/
</VirtualHost>

# HTTPS Virtual Host
<VirtualHost mycyclingcity.net:443>
    ServerName mycyclingcity.net
    
    # SSL Configuration
    SSLEngine on
    SSLCertificateFile /path/to/certificate.crt
    SSLCertificateKeyFile /path/to/private.key
    
    # Proxy to Gunicorn
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
    
    # Set X-Forwarded-Proto header
    RequestHeader set X-Forwarded-Proto "https"
    
    # Static Files
    Alias /static /data/var/mcc/staticfiles
    <Directory /data/var/mcc/staticfiles>
        Require all granted
        Options -Indexes
    </Directory>
    
    # Media Files
    Alias /media /data/var/mcc/media
    <Directory /data/var/mcc/media>
        Require all granted
        Options -Indexes
    </Directory>
    
    # Logs
    ErrorLog ${APACHE_LOG_DIR}/mcc_error.log
    CustomLog ${APACHE_LOG_DIR}/mcc_access.log combined
</VirtualHost>
```

Apache neu laden:
```bash
sudo systemctl reload apache2
# Oder
sudo service apache2 reload
```

## Schritt 12: Cronjobs einrichten

Füge folgende Cronjobs hinzu (z.B. in `/etc/crontab` oder `crontab -e`):

```cron
# MCC Worker - Speichert aktive Sessions in History (alle 5 Minuten)
*/5 * * * * cd /data/appl/mcc/mcc-web && /data/appl/mcc/venv/bin/python manage.py mcc_worker >> /data/var/mcc/logs/mcc_worker.log 2>&1

# Tägliches Datenbank-Backup um 2 Uhr
0 2 * * * cd /data/appl/mcc/mcc-web && /data/appl/mcc/venv/bin/python utils/backup_database.py --project-dir /data/appl/mcc/mcc-web --backup-dir /data/var/mcc/backups --keep-days 7 --compress >> /data/var/mcc/logs/backup.log 2>&1

# Wöchentliche Log-Bereinigung (Sonntag um 3 Uhr)
0 3 * * 0 cd /data/appl/mcc/mcc-web && /data/appl/mcc/venv/bin/python manage.py cleanup_application_logs >> /data/var/mcc/logs/cleanup.log 2>&1
```

## Schritt 13: Minecraft Worker (optional)

Falls Minecraft-Integration verwendet wird:

```bash
# Als Installationsbenutzer oder Laufzeitbenutzer
cd /data/appl/mcc/mcc-web

# Worker starten
./scripts/minecraft.sh start

# Snapshot Worker starten
./scripts/minecraft.sh snapshot-start
```

## Schritt 14: Verifizierung

1. **Health Check prüfen:**
   ```bash
   curl http://localhost:8001/health/
   ```

2. **Logs prüfen:**
   ```bash
   tail -f /data/var/mcc/logs/gunicorn_error.log
   tail -f /data/var/mcc/logs/api.log
   ```

3. **Prozesse prüfen:**
   ```bash
   ps aux | grep gunicorn
   cat /data/var/mcc/tmp/mcc-web.pid
   ```

## Update auf neue Version

1. **Backup erstellen:**
   ```bash
   cd /data/appl/mcc/mcc-web
   /data/appl/mcc/venv/bin/python utils/backup_database.py
   ```

2. **Neue Version extrahieren:**
   ```bash
   cd /data/appl/mcc
   tar -xzf mcc-web-deployment-1.1.0-20260125_120000.tar.gz
   ```

3. **Dependencies aktualisieren (falls nötig):**
   ```bash
   /data/appl/mcc/venv/bin/pip install -r mcc-web-1.1.0/requirements.txt
   ```

4. **Symlink aktualisieren:**
   ```bash
   cd /data/appl/mcc
   ln -sfn mcc-web-1.1.0 mcc-web
   ```

5. **Migrationen ausführen:**
   ```bash
   cd /data/appl/mcc/mcc-web
   /data/appl/mcc/venv/bin/python manage.py migrate
   ```

6. **Static Files aktualisieren:**
   ```bash
   /data/appl/mcc/venv/bin/python manage.py collectstatic --noinput
   ```

7. **Übersetzungen kompilieren:**
   ```bash
   /data/appl/mcc/venv/bin/python manage.py compilemessages
   ```

8. **Gunicorn neu laden:**
   ```bash
   ./scripts/reload_gunicorn.sh
   ```

9. **Testen und ggf. Rollback:**
   ```bash
   # Falls Probleme: Zurück zur alten Version
   cd /data/appl/mcc
   ln -sfn mcc-web-1.0.0 mcc-web
   ./mcc-web/scripts/reload_gunicorn.sh
   ```

## Rollback

Falls ein Rollback nötig ist:

```bash
# Als Installationsbenutzer
cd /data/appl/mcc

# Symlink auf alte Version setzen
ln -sfn mcc-web-1.0.0 mcc-web

# Gunicorn neu laden
./mcc-web/scripts/reload_gunicorn.sh
```

**Wichtig:** Alte Tabellen bleiben in der Datenbank erhalten, daher funktioniert der Rollback sofort.

## Troubleshooting

### Gunicorn startet nicht
- Prüfe Logs: `/data/var/mcc/logs/gunicorn_error.log`
- Prüfe PID-Datei: `/data/var/mcc/tmp/mcc-web.pid`
- Prüfe Berechtigungen auf `/data/var/mcc/tmp/`

### Datenbank-Fehler
- Prüfe Berechtigungen auf `/data/var/mcc/db/`
- Prüfe ob Datenbank existiert: `ls -la /data/var/mcc/db/`

### Static Files nicht erreichbar
- Prüfe Apache-Konfiguration
- Prüfe Berechtigungen auf `/data/var/mcc/staticfiles/`
- Führe `collectstatic` erneut aus

### .env wird nicht geladen
- Prüfe ob `.env` in `/data/appl/mcc/.env` existiert
- Prüfe Berechtigungen (sollte 640 sein)
- Prüfe ob Pfad in `settings.py` korrekt ist

## Weitere Informationen

- Deployment-Dokumentation: `docs/de/getting-started/DEPLOYMENT.md`
- Produktions-Checkliste: `docs/de/admin/PRODUCTION_CHECKLIST.md`
- Migration-Guide: `docs/de/admin/MIGRATION_RESET_GUIDE.md`
