# Fix für "no such table: django_session" Fehler

## Problem
Der Fehler `OperationalError: no such table: django_session` tritt auf, weil die `django_session` Tabelle nicht existiert.

## Lösung

### Option 1: Sessions Migrationen ausführen (empfohlen)

```bash
python manage.py migrate sessions
```

### Option 2: Alle Migrationen ausführen

```bash
python manage.py migrate
```

### Option 3: Management Command verwenden

```bash
python manage.py fix_sessions_table
```

Dieses Command prüft, ob die Tabelle existiert und führt die Migrationen aus, falls nötig.

## Nach dem Fix

Nachdem die `django_session` Tabelle erstellt wurde, sollte das Logging-System funktionieren:

1. Test-Logs generieren:
```bash
python manage.py test_logging
```

2. Im Admin prüfen:
   - Gehen Sie zu `/admin/mgmt/applicationlog/`
   - Warten Sie 5-6 Sekunden nach dem Test-Command

## Warum passiert das?

Die `django_session` Tabelle wird normalerweise von Django's `sessions` App erstellt. Wenn die Migrationen nicht ausgeführt wurden oder die Datenbank neu erstellt wurde, fehlt diese Tabelle.
