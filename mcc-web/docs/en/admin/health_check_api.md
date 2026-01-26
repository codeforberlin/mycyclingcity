# Health Check API for External Monitoring Systems

## Overview

The Health Check API endpoint allows external monitoring systems (Nagios, Icinga, Zabbix, etc.) to query the application status over HTTPS with API key authentication.

## Endpoint

```
GET /api/health/?api_key=YOUR_API_KEY
```

## Authentication

The endpoint requires an API key as a query parameter:

```
?api_key=your-secret-api-key
```

### Configure API Key

API keys are configured in the `.env` file:

```env
# Single API key
HEALTH_CHECK_API_KEYS=your-secret-api-key-here

# Multiple API keys (comma-separated)
HEALTH_CHECK_API_KEYS=key1,key2,key3
```

**Important**: In production, API keys should always be configured. Without configured keys, the endpoint is accessible in development but should be protected in production.

## Response Formats

### JSON Format (Default)

**Request:**
```
GET /api/health/?api_key=your-key&format=json
```

**Response (200 OK - All Good):**
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

**Response (200 OK - Warnings Present):**
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

**Response (503 Service Unavailable - Critical Errors):**
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

**Response (401 Unauthorized - Invalid API Key):**
```json
{
  "status": "error",
  "message": "Invalid or missing API key",
  "timestamp": "2026-01-22T17:30:00Z"
}
```

### Nagios Format (Plain Text)

**Request:**
```
GET /api/health/?api_key=your-key&format=nagios
```

**Response (200 OK):**
```
OK - Passed: 6, Warnings: 0, Errors: 0 | passed=6 warnings=0 errors=0 database_status=0 cache_status=0 disk_status=0 memory_status=0 static_files_status=0 media_files_status=0
```

**Response (200 OK - Warnings):**
```
WARNING - Passed: 4, Warnings: 2, Errors: 0 | passed=4 warnings=2 errors=0 database_status=0 cache_status=0 disk_status=1 memory_status=1 static_files_status=0 media_files_status=0

Details:
disk: WARNING - Disk usage high: 85.3%
memory: WARNING - Memory usage high: 82.5%
```

**Response (503 Service Unavailable - Critical Errors):**
```
CRITICAL - Passed: 4, Warnings: 1, Errors: 1 | passed=4 warnings=1 errors=1 database_status=2 cache_status=0 disk_status=1 memory_status=0 static_files_status=0 media_files_status=0

Details:
database: ERROR - Database error: connection refused
disk: WARNING - Disk usage high: 85.3%
```

## HTTP Status Codes

- **200 OK**: All checks passed or only warnings (no critical errors)
- **503 Service Unavailable**: Critical errors detected
- **401 Unauthorized**: Invalid or missing API key

## Query Parameters

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `api_key` | API key for authentication (required) | - | `?api_key=your-key` |
| `format` | Output format: `json` or `nagios` | `json` | `?format=nagios` |
| `detailed` | Include detailed check information | `true` | `?detailed=false` |

## Integration with Monitoring Systems

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

The endpoint can be monitored with Prometheus Blackbox Exporter:

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

## Security

### Best Practices

1. **Use Strong API Keys**: At least 32 characters, randomly generated
2. **Use HTTPS**: The endpoint should only be accessible over HTTPS
3. **Rotate API Keys**: Regularly generate new keys and remove old ones
4. **IP Whitelisting**: Additionally configure IP whitelisting in Apache/Nginx
5. **Rate Limiting**: Monitoring systems should not query too frequently (max. every 30 seconds)

### Generate API Key

```bash
# Generate random API key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Example .env Configuration

```env
# Health Check API Keys (comma-separated for multiple keys)
HEALTH_CHECK_API_KEYS=nagios-key-abc123xyz,icinga-key-def456uvw,zabbix-key-ghi789rst
```

## Troubleshooting

### 401 Unauthorized

- Check if the API key is correctly configured in the `.env` file
- Check if the API key is correctly passed in the request
- Check Django logs for errors

### 503 Service Unavailable

- Check detailed check information in the JSON response
- Check Django logs for specific errors
- Check server metrics in Admin GUI (`/admin/server/`)

### Endpoint Not Reachable

- Check if the endpoint is registered in `config/urls.py`
- Check Apache/Nginx configuration
- Check firewall rules

## Example Curl Requests

```bash
# JSON format
curl "https://mycyclingcity.net/api/health/?api_key=your-key&format=json"

# Nagios format
curl "https://mycyclingcity.net/api/health/?api_key=your-key&format=nagios"

# Without details
curl "https://mycyclingcity.net/api/health/?api_key=your-key&detailed=false"
```

## Performance

The Health Check endpoint is optimized for frequent queries:
- Fast database checks
- Efficient system metrics
- No blocking operations
- Low latency (< 100ms typical)

## Additional Information

- Server Control Dashboard: `/admin/server/` (for detailed metrics)
- Health Checks in Admin: `/admin/server/` (Health Check section)
- Logs: `/admin/logs/` (for error analysis)
