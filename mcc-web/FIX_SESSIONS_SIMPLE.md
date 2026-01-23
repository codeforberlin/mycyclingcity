# Einfache Lösung für "no such table: django_session"

## Problem
Die `django_session` Tabelle existiert nicht, aber Django denkt, die Migrationen seien bereits ausgeführt.

## Lösung 1: Command verwenden (empfohlen)

```bash
python manage.py fix_sessions_table
```

Dieses Command erstellt die Tabelle direkt, wenn sie fehlt.

## Lösung 2: Migrationen zurücksetzen und neu ausführen

```bash
# Migrationen als "nicht ausgeführt" markieren
python manage.py migrate sessions zero --fake

# Migrationen neu ausführen
python manage.py migrate sessions
```

## Lösung 3: Tabelle manuell erstellen (SQLite)

Wenn Sie SQLite verwenden, können Sie die Tabelle direkt erstellen:

```bash
sqlite3 db.sqlite3 <<EOF
CREATE TABLE IF NOT EXISTS django_session (
    session_key VARCHAR(40) PRIMARY KEY,
    session_data TEXT NOT NULL,
    expire_date DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS django_session_expire_date_a5c62663 
ON django_session(expire_date);
EOF
```

## Nach dem Fix

Nachdem die Tabelle erstellt wurde:

1. Test-Logs generieren:
```bash
python manage.py test_logging
```

2. Im Admin prüfen:
   - Gehen Sie zu `/admin/mgmt/applicationlog/`
   - Warten Sie 5-6 Sekunden nach dem Test-Command
