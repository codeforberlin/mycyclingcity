# Fail2ban-Konfiguration für MyCyclingCity

## Übersicht

Diese Fail2ban-Konfiguration schützt die MyCyclingCity Django-Anwendung vor verschiedenen Angriffen.

**WICHTIG**: Es gibt zwei Konfigurationsoptionen:

### Option 1: Apache-Level (EMPFOHLEN für Production)

Apache läuft als Reverse Proxy vor Gunicorn und sieht die originalen Client-IPs. Diese Konfiguration ist **empfohlen** für Production, weil:

- ✅ **Frühere Erkennung**: Angriffe werden bereits auf Apache-Ebene erkannt
- ✅ **Originale IPs**: Apache sieht die echten Client-IPs (Gunicorn sieht nur 127.0.0.1)
- ✅ **Weniger Last**: Gunicorn/Django werden nicht belastet
- ✅ **Umfassender Schutz**: Schützt auch statische Dateien und alle Apache-Endpunkte
- ✅ **Bessere Performance**: Blockierung erfolgt bevor Requests Django erreichen

**Jails:**
- `mcc-apache-auth`: Fehlgeschlagene Authentifizierungsversuche
- `mcc-apache-scanner`: Scanner/Prober (viele 404-Fehler)
- `mcc-apache-attack`: Angriffsversuche (SQL-Injection, XSS, etc.)
- `mcc-apache-bruteforce`: Bruteforce-Angriffe
- `mcc-apache-badbots`: Bekannte Bad Bots
- `mcc-apache-noscript`: Script/Datei-Scanner

### Option 2: Application-Level (Gunicorn/Django)

Diese Konfiguration überwacht Gunicorn- und Django-Logs direkt. Nützlich für:

- ✅ **Anwendungsspezifische Angriffe**: Erkennt Django-spezifische Fehler (z.B. API-Key-Fehler)
- ✅ **Detaillierte Logs**: Kann auf Django-Log-Meldungen reagieren
- ✅ **Fallback**: Wenn Apache-Logs nicht verfügbar sind

**Jails:**
- `mcc-django-auth`: Fehlgeschlagene Authentifizierungsversuche
- `mcc-django-scanner`: Scanner/Prober (viele 404-Fehler)
- `mcc-django-attack`: Angriffsversuche (SQL-Injection, XSS, etc.)
- `mcc-django-bruteforce`: Bruteforce-Angriffe
- `mcc-gunicorn-error`: Viele 500-Fehler

### Empfehlung

**Für Production**: Verwenden Sie **Apache-Level** (`install_fail2ban_apache.sh`)

**Für Development oder wenn Apache nicht verfügbar**: Verwenden Sie **Application-Level** (`install_fail2ban.sh`)

**Beide kombinieren**: Sie können beide Konfigurationen parallel verwenden für maximale Sicherheit (Apache-Level als primärer Schutz, Application-Level als zusätzliche Überwachung).

## Übersicht der Jails

- **mcc-django-auth**: Blockiert IPs bei fehlgeschlagenen Authentifizierungsversuchen
- **mcc-django-scanner**: Blockiert IPs die viele 404-Fehler verursachen (Scanner/Prober)
- **mcc-django-attack**: Blockiert IPs bei Angriffsversuchen (SQL-Injection, XSS, etc.)
- **mcc-django-bruteforce**: Blockiert IPs bei Bruteforce-Angriffen
- **mcc-gunicorn-error**: Blockiert IPs die viele 500-Fehler verursachen

## Installation

### Option 1: Apache-Level (EMPFOHLEN)

```bash
sudo bash /data/appl/mcc/mcc-web/scripts/install_fail2ban_apache.sh
```

### Option 2: Application-Level

```bash
sudo bash /data/appl/mcc/mcc-web/scripts/install_fail2ban.sh
```

### Manuelle Installation

#### Apache-Level

1. **Kopiere Jail-Konfiguration:**
   ```bash
   sudo cp /data/appl/mcc/mcc-web/scripts/mcc-fail2ban-apache.conf /etc/fail2ban/jail.d/mcc-apache.conf
   sudo chmod 644 /etc/fail2ban/jail.d/mcc-apache.conf
   ```

2. **Kopiere Filter-Dateien:**
   ```bash
   sudo cp /data/appl/mcc/mcc-web/scripts/filter.d/mcc-apache-*.conf /etc/fail2ban/filter.d/
   sudo chmod 644 /etc/fail2ban/filter.d/mcc-apache-*.conf
   ```

#### Application-Level

1. **Kopiere Jail-Konfiguration:**
   ```bash
   sudo cp /data/appl/mcc/mcc-web/scripts/mcc-fail2ban.conf /etc/fail2ban/jail.d/mcc.conf
   sudo chmod 644 /etc/fail2ban/jail.d/mcc.conf
   ```

2. **Kopiere Filter-Dateien:**
   ```bash
   sudo cp /data/appl/mcc/mcc-web/scripts/filter.d/mcc-django-*.conf /etc/fail2ban/filter.d/
   sudo cp /data/appl/mcc/mcc-web/scripts/filter.d/mcc-gunicorn-*.conf /etc/fail2ban/filter.d/
   sudo chmod 644 /etc/fail2ban/filter.d/mcc-*.conf
   ```

3. **Validiere Konfiguration:**
   ```bash
   sudo fail2ban-client -t
   ```

4. **Lade Fail2ban neu:**
   ```bash
   sudo systemctl reload fail2ban
   ```

## Konfiguration

### Jail-Parameter

Die Standardwerte können in `/etc/fail2ban/jail.d/mcc.conf` angepasst werden:

- **bantime**: Dauer des Banns (Standard: 3600 Sekunden = 1 Stunde)
- **findtime**: Zeitfenster für Fehlversuche (Standard: 600 Sekunden = 10 Minuten)
- **maxretry**: Anzahl der Fehlversuche vor Bann (Standard: 5)

### E-Mail-Benachrichtigungen

Um E-Mail-Benachrichtigungen zu aktivieren, füge in `/etc/fail2ban/jail.local` hinzu:

```ini
[DEFAULT]
destemail = admin@example.com
sendername = Fail2ban
action = %(action_)s
         %(action_mwl)s
```

## Testing

### Automatischer Test

Führen Sie das Test-Skript aus:

```bash
sudo bash /data/appl/mcc/mcc-web/scripts/test_fail2ban.sh
```

Das Skript führt folgende Tests durch:
1. Fail2ban Service Status
2. Verfügbare Jails auflisten
3. MCC-spezifische Jails prüfen
4. Filter-Validierung
5. Log-Pfade prüfen
6. Manueller Bann-Test (optional)
7. Fail2ban-Log prüfen
8. Konfiguration validieren

### Manuelle Tests

#### 1. Status prüfen

```bash
# Alle Jails anzeigen
sudo fail2ban-client status

# Spezifischen Jail prüfen
sudo fail2ban-client status mcc-django-auth
```

### Gebannte IPs anzeigen

```bash
# Alle gebannten IPs für einen Jail
sudo fail2ban-client get mcc-django-auth banned

# Alle gebannten IPs für alle Jails
sudo fail2ban-client status | grep "Banned IP"
```

### IP manuell bannen (Test)

```bash
# Test-IP bannen
sudo fail2ban-client set mcc-apache-auth banip 192.168.1.100

# Prüfen ob gebannt
sudo fail2ban-client get mcc-apache-auth banned

# Test-IP wieder entbannen
sudo fail2ban-client set mcc-apache-auth unbanip 192.168.1.100
```

### Filter testen

#### Automatischer Test aller Filter

Testet alle MCC-Filter gegen verfügbare Log-Dateien:

```bash
sudo bash /data/appl/mcc/mcc-web/scripts/test_fail2ban_filters.sh
```

#### Einzelnen Filter testen

Testet einen spezifischen Filter gegen eine Log-Datei:

```bash
# Apache-Filter testen
sudo bash /data/appl/mcc/mcc-web/scripts/test_fail2ban_filter_single.sh \
    mcc-apache-auth \
    /var/log/apache2/MCC_ssl_access_log.$(date +%Y%m%d)

# Django-Filter testen
sudo bash /data/appl/mcc/mcc-web/scripts/test_fail2ban_filter_single.sh \
    mcc-django-scanner \
    /data/var/mcc/logs/gunicorn_access.log
```

#### Manueller Filter-Test mit fail2ban-regex

```bash
# Apache-Filter testen
sudo fail2ban-regex /var/log/apache2/MCC_ssl_access_log.$(date +%Y%m%d) /etc/fail2ban/filter.d/mcc-apache-auth.conf

# Django-Filter testen
sudo fail2ban-regex /data/var/mcc/logs/gunicorn_access.log /etc/fail2ban/filter.d/mcc-django-auth.conf
```

### Test-Angriffe simulieren

**WICHTIG**: Verwenden Sie nur auf Test-Servern oder mit Test-IPs!

```bash
# Simuliere fehlgeschlagene Login-Versuche (5x für Bann)
for i in {1..5}; do
    curl -X POST https://your-domain.com/admin/login/ \
         -d "username=test&password=wrong" \
         -H "X-Forwarded-For: 192.168.1.100"
    sleep 1
done

# Prüfe ob IP gebannt wurde
sudo fail2ban-client get mcc-apache-auth banned
```

### Logs in Echtzeit überwachen

```bash
# Fail2ban-Log
sudo tail -f /var/log/fail2ban.log

# Apache Access-Log
sudo tail -f /var/log/apache2/MCC_ssl_access_log.$(date +%Y%m%d)

# Gunicorn Access-Log
sudo tail -f /data/var/mcc/logs/gunicorn_access.log
```

### IP manuell entbannen

```bash
# Einzelne IP entbannen
sudo fail2ban-client unban <IP-ADRESSE> -j mcc-django-auth

# Oder:
sudo fail2ban-client set mcc-django-auth unbanip <IP-ADRESSE>
```

### Alle IPs eines Jails entbannen

```bash
sudo fail2ban-client unban --all -j mcc-django-auth
```

### Jail neu starten

```bash
sudo fail2ban-client restart mcc-django-auth
```

## Logs

### Fail2ban-Logs

```bash
# Fail2ban-Log anzeigen
sudo tail -f /var/log/fail2ban.log

# Spezifischen Jail-Log anzeigen
sudo tail -f /var/log/fail2ban.log | grep mcc-django-auth
```

### Anwendungs-Logs

#### Apache-Level überwacht:
- `/var/log/apache2/MCC_ssl_access_log.*` - Apache SSL Access-Logs
- `/var/log/apache2/MCC_access_log.*` - Apache HTTP Access-Logs
- `/var/log/apache2/MCC_ssl_error_log.*` - Apache SSL Error-Logs
- `/var/log/apache2/MCC_error_log.*` - Apache HTTP Error-Logs

#### Application-Level überwacht:
- `/data/var/mcc/logs/django.log` - Django-Framework-Logs
- `/data/var/mcc/logs/gunicorn_access.log` - Gunicorn Access-Logs
- `/data/var/mcc/logs/gunicorn_error.log` - Gunicorn Error-Logs
- `/data/var/mcc/logs/api.log` - API-Logs

## Troubleshooting

### Jail ist nicht aktiv

1. **Prüfe ob Fail2ban läuft:**
   ```bash
   sudo systemctl status fail2ban
   ```

2. **Prüfe Konfiguration:**
   ```bash
   sudo fail2ban-client -t
   ```

3. **Prüfe Log-Dateien:**
   ```bash
   sudo tail -f /var/log/fail2ban.log
   ```

### Filter erkennt keine Angriffe

1. **Teste Filter manuell:**

   **Apache-Level:**
   ```bash
   sudo fail2ban-regex /var/log/apache2/MCC_ssl_access_log.$(date +%Y%m%d) /etc/fail2ban/filter.d/mcc-apache-auth.conf
   ```

   **Application-Level:**
   ```bash
   sudo fail2ban-regex /data/var/mcc/logs/gunicorn_access.log /etc/fail2ban/filter.d/mcc-django-auth.conf
   ```

2. **Prüfe Log-Format:**
   - **Apache Access-Log Format**: `%h %l %u %t "%r" %>s %b` oder `%h %l %u %t %{SSL_PROTOCOL}x %{SSL_CIPHER}x "%r" %>s %b`
   - **Gunicorn Access-Log Format**: `IP - - [timestamp] "METHOD /path HTTP/1.1" STATUS SIZE "referer" "user-agent" DURATION`
   - **Django-Log Format**: `[LEVEL] timestamp module process thread message`

### IP wird nicht gebannt

1. **Prüfe ob IP bereits gebannt ist:**
   ```bash
   sudo fail2ban-client get mcc-django-auth banned
   ```

2. **Prüfe ob IP auf Whitelist steht:**
   ```bash
   sudo fail2ban-client get mcc-django-auth ignoreip
   ```

3. **Prüfe Log-Dateien auf Fehler:**
   ```bash
   sudo tail -f /var/log/fail2ban.log
   ```

## Whitelist

Um IPs von der Bann-Liste auszunehmen, füge sie in `/etc/fail2ban/jail.local` hinzu:

```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24
```

Oder für einen spezifischen Jail:

```ini
[mcc-django-auth]
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24
```

## Deinstallation

```bash
# Entferne Jail-Konfiguration
sudo rm /etc/fail2ban/jail.d/mcc.conf

# Entferne Filter-Dateien
sudo rm /etc/fail2ban/filter.d/mcc-*.conf

# Lade Fail2ban neu
sudo systemctl reload fail2ban
```

## Weitere Informationen

- [Fail2ban Dokumentation](https://www.fail2ban.org/wiki/index.php/Main_Page)
- [Fail2ban Filter](https://www.fail2ban.org/wiki/index.php/Filters)
- [Fail2ban Actions](https://www.fail2ban.org/wiki/index.php/Actions)
