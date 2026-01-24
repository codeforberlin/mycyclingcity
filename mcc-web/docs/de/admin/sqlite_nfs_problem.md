# SQLite "disk I/O error" auf NFS - Problem und Lösungen

## Problem

**Fehler:**
```
sqlite3.OperationalError: disk I/O error
```

**Ursache:**
- SQLite-Datenbank liegt auf **NFS-Dateisystem** (`nas:/public-data`)
- Gunicorn läuft mit **mehreren Workern** (5 Worker)
- SQLite ist **NICHT für NFS** geeignet, besonders nicht mit mehreren gleichzeitigen Prozessen

## Warum SQLite auf NFS problematisch ist

1. **File Locking**: SQLite verwendet Datei-Locks, die auf NFS nicht zuverlässig funktionieren
2. **Concurrency**: Mehrere Worker-Prozesse greifen gleichzeitig auf die DB zu → Konflikte
3. **Network Latency**: NFS ist langsamer als lokales Dateisystem
4. **WAL-Mode**: Write-Ahead Logging funktioniert auf NFS nicht optimal

## Sofortige Lösung: Gunicorn mit 1 Worker

**Für sofortige Behebung:**

```bash
# Stoppen Sie Gunicorn
pkill gunicorn

# Starten Sie mit nur 1 Worker
gunicorn --workers 1 --threads 2 --bind 0.0.0.0:8001 config.wsgi:application
```

**Nachteile:**
- ❌ Keine Parallelisierung (nur 1 Request gleichzeitig)
- ❌ Nicht für Production mit hoher Last geeignet
- ✅ Funktioniert aber stabil auf NFS

## Mittelfristige Lösung: SQLite auf lokales Dateisystem

### Option 1: Datenbank auf lokales Dateisystem verschieben

```bash
# 1. Stoppen Sie Gunicorn
pkill gunicorn

# 2. Erstellen Sie lokales Verzeichnis
mkdir -p /tmp/mcc-db
chmod 755 /tmp/mcc-db

# 3. Kopieren Sie Datenbank
cp /nas/public/dev/mycyclingcity/mcc-web/data/db.sqlite3 /tmp/mcc-db/db.sqlite3

# 4. Ändern Sie settings.py
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': '/tmp/mcc-db/db.sqlite3',  # Lokales Dateisystem
#         'OPTIONS': {
#             'timeout': 30,
#         },
#     }
# }

# 5. Starten Sie Gunicorn neu
gunicorn --workers 5 --threads 2 --bind 0.0.0.0:8001 config.wsgi:application
```

**Vorteile:**
- ✅ Mehrere Worker möglich
- ✅ Bessere Performance
- ✅ Zuverlässigeres File Locking

**Nachteile:**
- ⚠️ Datenbank liegt auf `/tmp` (wird beim Neustart gelöscht!)
- ⚠️ Backup-Strategie erforderlich

### Option 2: Symlink auf lokales Dateisystem

```bash
# 1. Stoppen Sie Gunicorn
pkill gunicorn

# 2. Erstellen Sie lokales Verzeichnis
mkdir -p /var/lib/mcc-db
chmod 755 /var/lib/mcc-db

# 3. Verschieben Sie Datenbank
mv /nas/public/dev/mycyclingcity/mcc-web/data/db.sqlite3 /var/lib/mcc-db/db.sqlite3

# 4. Erstellen Sie Symlink
ln -s /var/lib/mcc-db/db.sqlite3 /nas/public/dev/mycyclingcity/mcc-web/data/db.sqlite3

# 5. Ändern Sie settings.py NICHT (Symlink wird automatisch verwendet)
```

## Langfristige Lösung: PostgreSQL/MySQL

**Für Production mit mehreren Workern ist eine echte Datenbank empfohlen:**

### PostgreSQL Setup

```python
# config/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'mcc_web',
        'USER': 'mcc_user',
        'PASSWORD': 'secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}
```

**Vorteile:**
- ✅ Perfekt für mehrere Worker
- ✅ Funktioniert auf NFS (wenn DB-Server lokal läuft)
- ✅ Bessere Performance
- ✅ ACID-konform
- ✅ Production-ready

## Empfohlene Vorgehensweise

### Sofort (heute):
1. Gunicorn mit 1 Worker starten (funktioniert sofort)
2. System stabilisieren

### Diese Woche:
1. Datenbank auf lokales Dateisystem verschieben
2. Gunicorn mit mehreren Workern starten
3. Backup-Strategie implementieren

### Nächster Monat:
1. PostgreSQL/MySQL evaluieren
2. Migration planen
3. Umstellung durchführen

## Aktuelle Konfiguration prüfen

```bash
# Prüfen Sie, ob Datenbank auf NFS liegt
df -h /nas/public/dev/mycyclingcity/mcc-web/data/db.sqlite3

# Prüfen Sie Gunicorn-Konfiguration
ps aux | grep gunicorn

# Prüfen Sie offene Datei-Handles
lsof data/db.sqlite3
```

## Weitere SQLite-Optimierungen (wenn auf lokalem FS)

Die aktuelle Konfiguration in `settings.py` ist bereits optimiert:
- ✅ WAL-Mode aktiviert
- ✅ Busy Timeout: 30 Sekunden
- ✅ Synchronous: NORMAL
- ✅ Cache Size: 64MB

Diese Einstellungen helfen, aber lösen das NFS-Problem nicht vollständig.

## Zusammenfassung

| Lösung | Worker | NFS | Production | Aufwand |
|--------|--------|-----|------------|---------|
| **1 Worker** | 1 | ✅ | ❌ | Sofort |
| **Lokales FS** | 5+ | ❌ | ⚠️ | Mittel |
| **PostgreSQL** | 5+ | ✅ | ✅ | Hoch |

**Empfehlung:** Für sofortige Behebung → 1 Worker. Für Production → PostgreSQL.
