# Maintenance Mode Setup

## Übersicht

Dieses Dokument beschreibt, wie der Maintenance Mode in der PROD-Umgebung funktioniert. Der Maintenance Mode wird durch **Django Middleware** gesteuert und bietet erweiterte Funktionen wie IP-Whitelist und Admin-Zugriff.

## Architektur

### Django Middleware (Hauptsteuerung)

Die **Django Middleware** (`mgmt.middleware_maintenance.MaintenanceModeMiddleware`) übernimmt die vollständige Kontrolle über den Maintenance Mode:

- ✅ Prüft die Maintenance-Flag-Datei
- ✅ Unterstützt IP-Whitelist (einzelne IPs und CIDR-Blöcke)
- ✅ Erlaubt Admin-Zugriff für Superuser
- ✅ Blockiert alle anderen Requests und leitet zur Maintenance-Seite um

### Apache ErrorDocument (Fallback)

Apache zeigt die Maintenance-Seite automatisch an, wenn Gunicorn nicht erreichbar ist (502/503/504 Fehler). Dies ist ein **Fallback-Mechanismus** für unerwartete Ausfälle.

## Dateien

- **Maintenance HTML**: `project_static/maintenance.html` (mit Login-Button)
- **Flag-Datei**: `/data/var/mcc/apache/.maintenance_mode`
- **Apache Config**: `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf`

## Apache-Konfiguration

### Schritt 1: Maintenance-Datei kopieren

```bash
# Auf dem PROD-Server
sudo cp /data/appl/mcc/mcc-web/project_static/maintenance.html /var/www/maintenance.html
sudo chown www-data:www-data /var/www/maintenance.html
sudo chmod 644 /var/www/maintenance.html
```

### Schritt 2: Apache-Konfiguration anpassen

In der Apache VirtualHost-Konfiguration (z.B. `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf`):

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    ServerAdmin <YOUR ADMIN CONTACT>
    DocumentRoot /var/www/

    # ... (bestehende Konfiguration) ...

    # Maintenance Mode: Nur für Gunicorn-Ausfälle (Fallback)
    # Django Middleware übernimmt die Hauptsteuerung
    ErrorDocument 502 /maintenance.html
    ErrorDocument 503 /maintenance.html
    ErrorDocument 504 /maintenance.html

    # Maintenance-Datei direkt ausliefern (ohne Proxy)
    Alias /maintenance.html /var/www/maintenance.html
    <Directory /var/www/>
        <Files "maintenance.html">
            Require all granted
        </Files>
    </Directory>

    # ... (bestehende ProxyPass-Regeln) ...
    ProxyPreserveHost On
    ProxyPass /maintenance.html !
    ProxyPass /static/ !
    ProxyPass /media/ !
    ProxyPass /robots.txt !
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

### Schritt 3: Apache neu laden

```bash
sudo apache2ctl configtest  # Konfiguration prüfen
sudo systemctl reload apache2
```

## Verwendung

### Maintenance Mode aktivieren/deaktivieren

**Über Admin GUI (empfohlen):**

1. Navigieren Sie zu **Mgmt** → **Maintenance Control**
2. Klicken Sie auf **Activate Maintenance Mode** oder **Deactivate Maintenance Mode**
3. Bestätigen Sie die Aktion

**Manuell (via Kommandozeile):**

```bash
# Maintenance aktivieren
touch /data/var/mcc/apache/.maintenance_mode
chmod 644 /data/var/mcc/apache/.maintenance_mode

# Maintenance deaktivieren
rm /data/var/mcc/apache/.maintenance_mode
```

**Status prüfen:**

```bash
if [ -f /data/var/mcc/apache/.maintenance_mode ]; then
    echo "Maintenance Mode: AKTIV"
else
    echo "Maintenance Mode: INAKTIV"
fi
```

## IP-Whitelist konfigurieren

### Über Admin GUI

1. Navigieren Sie zu **Mgmt** → **Maintenance Configurations**
2. Fügen Sie IP-Adressen oder CIDR-Blöcke hinzu (eine pro Zeile):
   ```
   192.168.1.100
   10.0.0.0/8
   172.16.0.0/12
   ```
3. Aktivieren Sie "Admin-Zugriff während Wartung erlauben" (falls gewünscht)
4. Speichern Sie die Konfiguration

### Unterstützte Formate

- **Einzelne IP**: `192.168.1.100`
- **CIDR-Block**: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.1.0/24`

## Verhalten während Maintenance Mode

### Erlaubte Zugriffe

- ✅ **Statische Dateien** (`/static/`) - Immer erreichbar
- ✅ **Media-Dateien** (`/media/`) - Immer erreichbar
- ✅ **Maintenance-Seite** (`/maintenance.html`) - Immer erreichbar
- ✅ **Admin-Bereich** (`/admin/`, `/de/admin/`) - Immer erreichbar (für Login)
- ✅ **IP-Whitelist** - Alle Seiten erreichbar, wenn IP in Whitelist
- ✅ **Superuser** - Alle Seiten erreichbar (wenn `allow_admin_during_maintenance=True`)

### Blockierte Zugriffe

- ❌ Alle anderen Seiten (werden zur Maintenance-Seite umgeleitet)

## Logs

### Django Middleware Logs

Die Middleware-Logs werden in `/data/var/mcc/logs/mgmt.log` geschrieben:

```bash
# Middleware-Logs in Echtzeit anzeigen
tail -f /data/var/mcc/logs/mgmt.log | grep MaintenanceMode

# Beispiel-Logs:
# INFO [MaintenanceMode] Redirecting IP 141.15.25.200 to maintenance page (path: /de/map/)
# DEBUG [MaintenanceMode] Allowing admin access (path: /admin/)
# DEBUG [MaintenanceMode] Allowing access for superuser admin from IP 84.132.227.73 (path: /de/map/)
```

### Log-Level

- **INFO**: Requests werden zur Maintenance-Seite umgeleitet
- **DEBUG**: Admin-Zugriff oder IP-Whitelist erlaubt Zugriff
- **WARNING**: Fehler bei der Konfiguration (Fallback-Verhalten)
- **ERROR**: Kritische Fehler

## Testing

### Test 1: Maintenance Mode aktivieren

```bash
# Maintenance aktivieren (via Admin GUI oder Kommandozeile)
touch /data/var/mcc/apache/.maintenance_mode
chmod 644 /data/var/mcc/apache/.maintenance_mode

# Website aufrufen - sollte Maintenance-Seite zeigen
curl -I https://mycyclingcity.net/de/map/
# Erwartet: HTTP/1.1 302 Found (Redirect zu /maintenance.html)

# Admin-Zugriff testen
curl -I https://mycyclingcity.net/admin/
# Erwartet: HTTP/1.1 200 OK (Login-Seite erreichbar)
```

### Test 2: IP-Whitelist

```bash
# IP zur Whitelist hinzufügen (via Admin GUI)
# Dann von dieser IP aus testen:
curl -I https://mycyclingcity.net/de/map/
# Erwartet: HTTP/1.1 200 OK (Zugriff erlaubt)
```

### Test 3: Superuser-Zugriff

```bash
# Als Superuser einloggen
# Dann testen:
curl -I -H "Cookie: sessionid=..." https://mycyclingcity.net/de/map/
# Erwartet: HTTP/1.1 200 OK (Zugriff erlaubt)
```

### Test 4: Gunicorn-Ausfall (Apache Fallback)

```bash
# Gunicorn stoppen
sudo systemctl stop mcc-web  # oder entsprechendes

# Website aufrufen - sollte Maintenance-Seite zeigen (via Apache ErrorDocument)
curl -I https://mycyclingcity.net/
# Erwartet: HTTP/1.1 502 Bad Gateway oder 503 Service Unavailable

# Gunicorn starten
sudo systemctl start mcc-web

# Website aufrufen - sollte normal funktionieren
curl -I https://mycyclingcity.net/
# Erwartet: HTTP/1.1 200 OK
```

## Troubleshooting

### Maintenance-Seite wird nicht angezeigt

1. **Prüfen, ob Flag-Datei existiert:**
   ```bash
   ls -la /data/var/mcc/apache/.maintenance_mode
   ```

2. **Prüfen, ob Django Middleware aktiv ist:**
   ```bash
   # In settings.py sollte stehen:
   # 'mgmt.middleware_maintenance.MaintenanceModeMiddleware'
   grep -r "MaintenanceModeMiddleware" /data/appl/mcc/mcc-web/config/settings.py
   ```

3. **Prüfen, ob Apache RewriteRule die Requests abfängt:**
   ```bash
   # Sollte KEINE RewriteRule für .maintenance_mode geben
   grep -r "maintenance_mode\|RewriteCond.*maintenance" /etc/apache2/sites-available/
   ```

4. **Django-Logs prüfen:**
   ```bash
   tail -50 /data/var/mcc/logs/mgmt.log | grep MaintenanceMode
   ```

### Admin-Zugriff funktioniert nicht

1. **Prüfen, ob `/admin/` erreichbar ist:**
   ```bash
   curl -I https://mycyclingcity.net/admin/
   # Sollte: HTTP/1.1 200 OK (nicht 302 Redirect)
   ```

2. **Prüfen, ob `allow_admin_during_maintenance=True`:**
   - Admin GUI → **Mgmt** → **Maintenance Configurations**
   - Prüfen Sie "Admin-Zugriff während Wartung erlauben"

3. **Prüfen, ob Benutzer Superuser ist:**
   - Admin GUI → **Authentication and Authorization** → **Users**
   - Prüfen Sie "Superuser status"

### IP-Whitelist funktioniert nicht

1. **Prüfen, ob IP korrekt eingegeben wurde:**
   - Eine IP pro Zeile
   - Keine Leerzeichen
   - Korrektes Format (z.B. `192.168.1.100` oder `10.0.0.0/8`)

2. **Prüfen, ob Client-IP korrekt erkannt wird:**
   ```bash
   # In den Logs sollte die Client-IP erscheinen
   tail -f /data/var/mcc/logs/mgmt.log | grep MaintenanceMode
   ```

3. **Bei Proxy/Load Balancer:**
   - Die IP wird aus `X-Forwarded-For` Header gelesen
   - Prüfen Sie, ob Apache den Header korrekt weiterleitet

### Django-Logs zeigen keine Einträge

1. **Prüfen, ob Requests Django erreichen:**
   ```bash
   # Wenn Apache RewriteRule aktiv ist, erreichen Requests Django nicht
   # Entfernen Sie alle RewriteRule-Konfigurationen für Maintenance
   ```

2. **Prüfen, ob Log-Level korrekt ist:**
   - Middleware verwendet `logger.info()` und `logger.debug()`
   - Log-Level sollte mindestens `INFO` sein

## Wichtige Hinweise

1. **Apache RewriteRule deaktivieren**: Apache sollte **KEINE** RewriteRule für die Maintenance-Flag-Datei verwenden, da dies die Django Middleware blockiert.

2. **IP-Whitelist**: Die IP-Whitelist funktioniert nur, wenn Django die Kontrolle hat. Wenn Apache die Requests abfängt, funktioniert die IP-Whitelist nicht.

3. **Admin-Zugriff**: Superuser können auf alle Seiten zugreifen, wenn `allow_admin_during_maintenance=True` aktiviert ist.

4. **Maintenance-Seite**: Die Maintenance-Seite (`/maintenance.html`) hat einen Login-Button, damit sich Admins einloggen können.

5. **Logs**: Alle Middleware-Aktivitäten werden in `/data/var/mcc/logs/mgmt.log` protokolliert.

## Empfehlung

**Für PROD-Umgebung:**

- ✅ **Django Middleware** für geplante Wartungen (mit IP-Whitelist und Admin-Zugriff)
- ✅ **Apache ErrorDocument** als Fallback für unerwartete Gunicorn-Ausfälle
- ❌ **KEINE Apache RewriteRule** für Maintenance-Flag-Datei

Diese Konfiguration bietet maximale Flexibilität und Funktionalität.
