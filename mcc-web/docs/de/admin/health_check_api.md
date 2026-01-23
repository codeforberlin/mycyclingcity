# Health Check API für externe Monitoring-Systeme

## Übersicht

Der Health Check API Endpoint ermöglicht es externen Monitoring-Systemen (Nagios, Icinga, Zabbix, etc.), den Status der Anwendung über HTTPS mit API-Key-Authentifizierung abzufragen.

## Endpoint

```
GET /api/health/?api_key=YOUR_API_KEY
```

## Authentifizierung

Der Endpoint erfordert einen API-Key als Query-Parameter:

```
?api_key=your-secret-api-key
```

### API-Key konfigurieren

Die API-Keys werden in der `.env` Datei konfiguriert:

```env
# Einzelner API-Key
HEALTH_CHECK_API_KEYS=your-secret-api-key-here

# Mehrere API-Keys (komma-separiert)
HEALTH_CHECK_API_KEYS=key1,key2,key3
```

**Wichtig**: In der Produktion sollten immer API-Keys konfiguriert werden. Ohne konfigurierte Keys ist der Endpoint in der Entwicklung zugänglich, sollte aber in Produktion geschützt sein.

## Response-Formate

### JSON-Format (Standard)

**Request:**
```
GET /api/health/?api_key=your-key&format=json
```

**Response (200 OK - Alles in Ordnung):**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-22T17:30:00Z",
  "checks_passed": 6,
  "checks_warning": 0,
  "checks_error": 0,
  "checks": {
    "database": {
      "status": "ok",
      "message": "Database connection successful"
    },
    "cache": {
      "status": "ok",
      "message": "Cache is working"
    },
    "disk": {
      "status": "ok",
      "message": "Disk usage: 45.2%"
    },
    "memory": {
      "status": "ok",
      "message": "Memory usage: 62.1%"
    },
    "static_files": {
      "status": "ok",
      "message": "Static files directory exists: /path/to/static"
    },
    "media_files": {
      "status": "ok",
      "message": "Media files directory exists: /path/to/media"
    }
  }
}
```

**Response (200 OK - Warnungen vorhanden):**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-22T17:30:00Z",
  "checks_passed": 4,
  "checks_warning": 2,
  "checks_error": 0,
  "checks": {
    "disk": {
      "status": "warning",
      "message": "Disk usage high: 85.3%"
    },
    "memory": {
      "status": "warning",
      "message": "Memory usage high: 82.5%"
    }
  }
}
```

**Response (503 Service Unavailable - Kritische Fehler):**
```json
{
  "status": "unhealthy",
  "timestamp": "2026-01-22T17:30:00Z",
  "checks_passed": 4,
  "checks_warning": 1,
  "checks_error": 1,
  "checks": {
    "database": {
      "status": "error",
      "message": "Database error: connection refused"
    }
  }
}
```

**Response (401 Unauthorized - Ungültiger API-Key):**
```json
{
  "status": "error",
  "message": "Invalid or missing API key",
  "timestamp": "2026-01-22T17:30:00Z"
}
```

### Nagios-Format (Plain Text)

**Request:**
```
GET /api/health/?api_key=your-key&format=nagios
```

**Response (200 OK):**
```
OK - Passed: 6, Warnings: 0, Errors: 0 | passed=6 warnings=0 errors=0 database_status=0 cache_status=0 disk_status=0 memory_status=0 static_files_status=0 media_files_status=0
```

**Response (200 OK - Warnungen):**
```
WARNING - Passed: 4, Warnings: 2, Errors: 0 | passed=4 warnings=2 errors=0 database_status=0 cache_status=0 disk_status=1 memory_status=1 static_files_status=0 media_files_status=0

Details:
disk: WARNING - Disk usage high: 85.3%
memory: WARNING - Memory usage high: 82.5%
```

**Response (503 Service Unavailable - Kritische Fehler):**
```
CRITICAL - Passed: 4, Warnings: 1, Errors: 1 | passed=4 warnings=1 errors=1 database_status=2 cache_status=0 disk_status=1 memory_status=0 static_files_status=0 media_files_status=0

Details:
database: ERROR - Database error: connection refused
disk: WARNING - Disk usage high: 85.3%
```

## HTTP Status Codes

- **200 OK**: Alle Checks bestanden oder nur Warnungen (keine kritischen Fehler)
- **503 Service Unavailable**: Kritische Fehler erkannt
- **401 Unauthorized**: Ungültiger oder fehlender API-Key

## Query-Parameter

| Parameter | Beschreibung | Standard | Beispiel |
|----------|--------------|----------|----------|
| `api_key` | API-Key für Authentifizierung (erforderlich) | - | `?api_key=your-key` |
| `format` | Ausgabeformat: `json` oder `nagios` | `json` | `?format=nagios` |
| `detailed` | Detaillierte Check-Informationen einbeziehen | `true` | `?detailed=false` |

## Integration mit Monitoring-Systemen

### Nagios

**Check Command Definition (`commands.cfg`):**
```cfg
define command {
    command_name    check_mcc_web_health
    command_line    /usr/lib/nagios/plugins/check_http -H mycyclingcity.net -S -u "/api/health/?api_key=YOUR_API_KEY&format=nagios" -e 200,503
}
```

**Service Definition (`services.cfg`):**
```cfg
define service {
    use                     generic-service
    host_name               mycyclingcity.net
    service_description     MCC-Web Health Check
    check_command           check_mcc_web_health
    check_interval          5
    retry_interval          1
    max_check_attempts      3
}
```

### Icinga2

**Check Command:**
```bash
/usr/lib/nagios/plugins/check_http -H mycyclingcity.net -S -u "/api/health/?api_key=YOUR_API_KEY&format=nagios" -e 200,503
```

**Icinga2 Service:**
```icinga2
object Service "mcc-web-health" {
    import "generic-service"
    host_name = "mycyclingcity.net"
    check_command = "http"
    vars.http_address = "mycyclingcity.net"
    vars.http_uri = "/api/health/?api_key=YOUR_API_KEY&format=nagios"
    vars.http_expect = "200,503"
    vars.http_ssl = true
}
```

### Zabbix

**HTTP Agent Item:**
- **Name**: MCC-Web Health Check
- **Type**: HTTP Agent
- **URL**: `https://mycyclingcity.net/api/health/?api_key=YOUR_API_KEY&format=json`
- **Request Method**: GET
- **Status Codes**: 200,503

**Trigger:**
```
{mycyclingcity.net:web.test.fail[mcc-web-health].str(CRITICAL)}=1
```

### Prometheus / Grafana

Der Endpoint kann mit Prometheus Blackbox Exporter überwacht werden:

```yaml
scrape_configs:
  - job_name: 'mcc-web-health'
    metrics_path: /api/health/
    params:
      api_key: ['YOUR_API_KEY']
      format: ['json']
    static_configs:
      - targets:
        - mycyclingcity.net:443
    relabel_configs:
      - source_labels: [__param_target]
        target_label: instance
```

## Sicherheit

### Best Practices

1. **Starke API-Keys verwenden**: Mindestens 32 Zeichen, zufällig generiert
2. **HTTPS verwenden**: Der Endpoint sollte nur über HTTPS erreichbar sein
3. **API-Keys rotieren**: Regelmäßig neue Keys generieren und alte entfernen
4. **IP-Whitelisting**: Zusätzlich IP-Whitelisting in Apache/Nginx konfigurieren
5. **Rate Limiting**: Monitoring-Systeme sollten nicht zu häufig abfragen (max. alle 30 Sekunden)

### API-Key generieren

```bash
# Zufälligen API-Key generieren
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Beispiel .env Konfiguration

```env
# Health Check API Keys (komma-separiert für mehrere Keys)
HEALTH_CHECK_API_KEYS=nagios-key-abc123xyz,icinga-key-def456uvw,zabbix-key-ghi789rst
```

## Troubleshooting

### 401 Unauthorized

- Prüfen Sie, ob der API-Key korrekt in der `.env` Datei konfiguriert ist
- Prüfen Sie, ob der API-Key im Request korrekt übergeben wird
- Prüfen Sie die Django-Logs für Fehler

### 503 Service Unavailable

- Prüfen Sie die detaillierten Check-Informationen im JSON-Response
- Prüfen Sie die Django-Logs für spezifische Fehler
- Prüfen Sie die Server-Metriken im Admin GUI (`/admin/server/`)

### Endpoint nicht erreichbar

- Prüfen Sie, ob der Endpoint in `config/urls.py` registriert ist
- Prüfen Sie die Apache/Nginx-Konfiguration
- Prüfen Sie die Firewall-Regeln

## Beispiel-Curl-Requests

```bash
# JSON-Format
curl "https://mycyclingcity.net/api/health/?api_key=your-key&format=json"

# Nagios-Format
curl "https://mycyclingcity.net/api/health/?api_key=your-key&format=nagios"

# Ohne Details
curl "https://mycyclingcity.net/api/health/?api_key=your-key&detailed=false"
```

## Performance

Der Health Check Endpoint ist optimiert für häufige Abfragen:
- Schnelle Datenbank-Checks
- Effiziente System-Metriken
- Keine Blocking-Operationen
- Geringe Latenz (< 100ms typisch)

## Weitere Informationen

- Server Control Dashboard: `/admin/server/` (für detaillierte Metriken)
- Health Checks im Admin: `/admin/server/` (Health Check Sektion)
- Logs: `/admin/logs/` (für Fehleranalyse)
