# Apache Maintenance Mode Setup

## Übersicht

Dieses Dokument beschreibt, wie die Maintenance-Seite (`maintenance.html`) in der PROD-Umgebung aktiviert wird, um während Wartungsarbeiten eine professionelle Wartungsseite anzuzeigen.

## Dateien

- **Maintenance HTML**: `project_static/maintenance.html`
- **Apache Config**: `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf` (oder ähnlich)

## Vorgehensweise

### Option 1: Apache ErrorDocument (Empfohlen)

Die einfachste Methode ist, Apache so zu konfigurieren, dass bei einem Fehler (z.B. wenn Gunicorn nicht erreichbar ist) die Maintenance-Seite angezeigt wird.

#### Schritt 1: Maintenance-Datei kopieren

```bash
# Auf dem PROD-Server
sudo cp /data/games/mcc/mcc-web/project_static/maintenance.html /var/www/maintenance.html
sudo chown www-data:www-data /var/www/maintenance.html
sudo chmod 644 /var/www/maintenance.html
```

#### Schritt 2: Apache-Konfiguration anpassen

In der Apache VirtualHost-Konfiguration (z.B. `/etc/apache2/sites-available/mycyclingcity.net-ssl.conf`) **VOR** den ProxyPass-Regeln hinzufügen:

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    ServerAdmin <YOUR ADMIN CONTACT>
    DocumentRoot /var/www/

    # ... (bestehende Konfiguration) ...

    # Maintenance Mode: Wenn Gunicorn nicht erreichbar ist, zeige Maintenance-Seite
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
    ProxyPass /robots.txt !
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

#### Schritt 3: Apache neu laden

```bash
sudo apache2ctl configtest  # Konfiguration prüfen
sudo systemctl reload apache2
```

**Vorteile:**
- Automatisch aktiv, wenn Gunicorn nicht erreichbar ist
- Keine manuelle Aktivierung nötig
- Funktioniert auch bei unerwarteten Ausfällen

---

### Option 2: Manueller Maintenance-Mode mit RewriteRule

Für geplante Wartungsarbeiten kann ein manueller Maintenance-Mode eingerichtet werden.

#### Schritt 1: Maintenance-Flag-Datei erstellen

**Hinweis:** Die Maintenance-Flag-Datei kann jetzt auch über das Admin GUI gesteuert werden (siehe "Mgmt" → "Maintenance Control").

**Manuell (via Kommandozeile):**

```bash
# Maintenance aktivieren
sudo touch /data/var/mcc/apache/.maintenance_mode
sudo chmod 644 /data/var/mcc/apache/.maintenance_mode

# Maintenance deaktivieren
sudo rm /data/var/mcc/apache/.maintenance_mode
```

**Über Admin GUI (empfohlen):**

1. Navigieren Sie zu **Mgmt** → **Maintenance Control**
2. Klicken Sie auf **Activate Maintenance Mode** oder **Deactivate Maintenance Mode**
3. Bestätigen Sie die Aktion

#### Schritt 2: Apache-Konfiguration anpassen

In der Apache VirtualHost-Konfiguration **VOR** den ProxyPass-Regeln:

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    # ... (bestehende Konfiguration) ...

    # Maintenance Mode: Prüfe auf Flag-Datei
    RewriteEngine On
    
    # Wenn Maintenance-Flag existiert UND nicht /maintenance.html oder /static/ angefragt wird
    RewriteCond /data/var/mcc/apache/.maintenance_mode -f
    RewriteCond %{REQUEST_URI} !^/maintenance\.html$
    RewriteCond %{REQUEST_URI} !^/static/
    RewriteRule ^(.*)$ /maintenance.html [R=503,L]

    # Maintenance-Datei direkt ausliefern
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
    ProxyPass /robots.txt !
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

**Hinweis:** Für RewriteRule muss das `rewrite`-Modul aktiviert sein:
```bash
sudo a2enmod rewrite
```

#### Schritt 3: Apache neu laden

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

**Vorteile:**
- Manuelle Kontrolle über Wartungszeiten
- Kann vor geplanten Wartungsarbeiten aktiviert werden
- Statische Dateien bleiben erreichbar (optional konfigurierbar)

**Nachteile:**
- Muss manuell aktiviert/deaktiviert werden
- Vergessene Deaktivierung blockiert die gesamte Website

---

### Option 3: Kombiniert (Automatisch + Manuell)

Kombination beider Methoden für maximale Flexibilität:

```apache
<VirtualHost *:443>
    ServerName mycyclingcity.net
    # ... (bestehende Konfiguration) ...

    RewriteEngine On
    
    # Manueller Maintenance-Mode (hat Priorität)
    RewriteCond /data/var/mcc/apache/.maintenance_mode -f
    RewriteCond %{REQUEST_URI} !^/maintenance\.html$
    RewriteCond %{REQUEST_URI} !^/static/
    RewriteRule ^(.*)$ /maintenance.html [R=503,L]

    # Automatischer Maintenance-Mode bei Proxy-Fehlern
    ErrorDocument 502 /maintenance.html
    ErrorDocument 503 /maintenance.html
    ErrorDocument 504 /maintenance.html

    # Maintenance-Datei direkt ausliefern
    Alias /maintenance.html /var/www/maintenance.html
    <Directory /var/www/>
        <Files "maintenance.html">
            Require all granted
        </Files>
    </Directory>

    # ... (bestehende ProxyPass-Regeln) ...
</VirtualHost>
```

---

## Verwendung

### Automatischer Mode (Option 1)

- **Aktivierung**: Automatisch, wenn Gunicorn nicht erreichbar ist
- **Deaktivierung**: Automatisch, wenn Gunicorn wieder erreichbar ist

### Manueller Mode (Option 2)

**Wartung starten (Admin GUI - empfohlen):**
1. Navigieren Sie zu **Mgmt** → **Maintenance Control**
2. Klicken Sie auf **Activate Maintenance Mode**
3. Bestätigen Sie die Aktion

**Wartung starten (Kommandozeile):**
```bash
sudo touch /data/var/mcc/apache/.maintenance_mode
sudo chmod 644 /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2
```

**Wartung beenden (Admin GUI - empfohlen):**
1. Navigieren Sie zu **Mgmt** → **Maintenance Control**
2. Klicken Sie auf **Deactivate Maintenance Mode**
3. Bestätigen Sie die Aktion

**Wartung beenden (Kommandozeile):**
```bash
sudo rm /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2
```

**Status prüfen:**
```bash
if [ -f /data/var/mcc/apache/.maintenance_mode ]; then
    echo "Maintenance Mode: AKTIV"
else
    echo "Maintenance Mode: INAKTIV"
fi
```

---

## Erweiterte Konfiguration

### Statische Dateien während Wartung erlauben

Wenn CSS/JS/Images auch während der Wartung erreichbar sein sollen:

```apache
# In der RewriteRule: /static/ bereits ausgeschlossen
RewriteCond %{REQUEST_URI} !^/static/
```

### Admin-Zugriff während Wartung erlauben

Für Notfälle kann der Admin-Zugriff während der Wartung erlaubt werden:

```apache
# IP-basierte Ausnahme (ersetze YOUR_IP mit der Admin-IP)
RewriteCond %{REMOTE_ADDR} !^YOUR_IP$
RewriteCond /data/var/mcc/apache/.maintenance_mode -f
RewriteCond %{REQUEST_URI} !^/maintenance\.html$
RewriteCond %{REQUEST_URI} !^/static/
RewriteRule ^(.*)$ /maintenance.html [R=503,L]
```

### Custom HTTP Status Code

Standardmäßig wird `503 Service Unavailable` verwendet. Dies signalisiert Suchmaschinen, dass die Wartung temporär ist.

---

## Testing

### Test 1: Automatischer Mode

```bash
# Gunicorn stoppen
sudo systemctl stop mcc-web  # oder entsprechendes

# Website aufrufen - sollte Maintenance-Seite zeigen
curl -I https://mycyclingcity.net/
# Erwartet: HTTP/1.1 502 Bad Gateway oder 503 Service Unavailable

# Gunicorn starten
sudo systemctl start mcc-web

# Website aufrufen - sollte normal funktionieren
curl -I https://mycyclingcity.net/
# Erwartet: HTTP/1.1 200 OK
```

### Test 2: Manueller Mode

```bash
# Maintenance aktivieren (via Admin GUI oder Kommandozeile)
sudo touch /data/var/mcc/apache/.maintenance_mode
sudo chmod 644 /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2

# Website aufrufen
curl -I https://mycyclingcity.net/
# Erwartet: HTTP/1.1 503 Service Unavailable

# Maintenance deaktivieren (via Admin GUI oder Kommandozeile)
sudo rm /data/var/mcc/apache/.maintenance_mode
sudo systemctl reload apache2

# Website aufrufen
curl -I https://mycyclingcity.net/
# Erwartet: HTTP/1.1 200 OK
```

---

## Empfehlung

**Für PROD-Umgebung empfohlen: Option 1 (Automatisch) oder Option 3 (Kombiniert)**

- **Option 1**: Einfach, automatisch, keine manuelle Intervention nötig
- **Option 3**: Maximale Flexibilität, automatisch bei Ausfällen, manuell bei geplanten Wartungen

---

## Wichtige Hinweise

1. **Backup**: Vor Änderungen an der Apache-Konfiguration immer ein Backup erstellen
2. **Testen**: Änderungen zuerst in einer Test-Umgebung testen
3. **Monitoring**: Während Wartungsarbeiten die Logs überwachen
4. **Kommunikation**: Benutzer über geplante Wartungsarbeiten informieren (z.B. per E-Mail, Social Media)

---

## Troubleshooting

### Maintenance-Seite wird nicht angezeigt

1. Prüfen, ob Maintenance-Flag existiert: `ls -la /data/var/mcc/apache/.maintenance_mode`
2. Prüfen, ob Apache die Flag-Datei lesen kann: `sudo -u www-data test -f /data/var/mcc/apache/.maintenance_mode && echo "OK" || echo "FEHLER"`
3. Prüfen, ob Maintenance-HTML existiert: `ls -la /var/www/maintenance.html`
4. Prüfen, ob Apache die HTML-Datei lesen kann: `sudo -u www-data cat /var/www/maintenance.html`
5. Prüfen, ob Alias korrekt ist: `apache2ctl -S`
6. Apache Error-Log prüfen: `sudo tail -f /var/log/apache2/MCC_ssl_error_log.*`

### Apache startet nicht nach Änderungen

1. Konfiguration prüfen: `sudo apache2ctl configtest`
2. Syntax-Fehler beheben
3. Modul aktiviert? `sudo a2enmod rewrite` (falls RewriteRule verwendet)

### Statische Dateien werden blockiert

- In RewriteRule sicherstellen, dass `/static/` ausgeschlossen ist
- Prüfen, ob `ProxyPass /static/ !` korrekt gesetzt ist
