# Fix für Session Migration Problem

## Problem
Die Migration `game.0003_session_alter_gamesession_options` versucht, die Tabelle `django_session` zu erstellen, die aber bereits existiert.

## Lösung

### Option 1: Migration als "fake" ausführen (empfohlen)

Wenn die Tabelle `django_session` bereits existiert, führen Sie die Migration als "fake" aus:

```bash
python manage.py migrate game 0003_session_alter_gamesession_options --fake
```

Dann führen Sie die restlichen Migrationen aus:
```bash
python manage.py migrate
```

### Option 2: Migration manuell anpassen

Die Migration wurde bereits angepasst, um die Tabelle nicht zu erstellen, wenn sie bereits existiert. Sie können jetzt einfach ausführen:

```bash
python manage.py migrate
```

## Für das Logging-System

Die `mgmt` Migration kann separat ausgeführt werden:

```bash
python manage.py migrate mgmt
```

Dies sollte funktionieren, auch wenn die `game` Migration noch aussteht.
