# Übersetzungen kompilieren (ohne venv-Bibliotheken)

Standardmäßig kompiliert `python manage.py compilemessages` **alle** gefundenen `.po`-Dateien, einschließlich derer von installierten Bibliotheken im venv. Das ist normalerweise nicht nötig und kann Zeit sparen.

## Lösung: Nur Projekt-Übersetzungen kompilieren

### Methode 1: Makefile verwenden (Empfohlen)

```bash
make compilemessages
```

Dies kompiliert nur die Übersetzungen für `de` und `en` aus dem Projekt-Verzeichnis (`locale/`).

### Methode 2: Script verwenden

```bash
./scripts/compilemessages_project_only.sh
```

Oder für eine bestimmte Sprache:

```bash
./scripts/compilemessages_project_only.sh de
./scripts/compilemessages_project_only.sh en
```

### Methode 3: Direkt mit manage.py (nur bestimmte Sprachen)

```bash
python manage.py compilemessages --locale de --locale en
```

Dies kompiliert nur die angegebenen Sprachen und ignoriert automatisch die venv-Bibliotheken, da `LOCALE_PATHS` in `settings.py` nur auf `BASE_DIR / 'locale'` verweist.

### Methode 4: Custom Management Command

```bash
python manage.py compilemessages_custom
```

Dieses Command kompiliert nur Übersetzungen aus `LOCALE_PATHS` und schließt explizit venv-Verzeichnisse aus.

## Warum funktioniert das?

In `config/settings.py` ist `LOCALE_PATHS` bereits korrekt konfiguriert:

```python
LOCALE_PATHS = [
    BASE_DIR / 'locale',  # Nur Projekt-Verzeichnis
]
```

Wenn Sie `compilemessages` mit `--locale` verwenden, werden nur die Übersetzungen aus `LOCALE_PATHS` für die angegebenen Sprachen kompiliert.

## Standard-Verhalten ändern

Falls Sie möchten, dass `compilemessages` standardmäßig nur Projekt-Übersetzungen kompiliert, können Sie:

1. **Alias erstellen** (in `~/.bashrc` oder `~/.zshrc`):
   ```bash
   alias compilemessages='python manage.py compilemessages --locale de --locale en'
   ```

2. **Makefile verwenden** (bereits eingerichtet):
   ```bash
   make compilemessages
   ```

## Alle Übersetzungen kompilieren (inkl. venv)

Falls Sie doch alle Übersetzungen kompilieren möchten (z.B. für Debugging):

```bash
make compilemessages-all
# oder
python manage.py compilemessages
```

## Verifizierung

Prüfen Sie, welche `.mo`-Dateien erstellt wurden:

```bash
# Nur Projekt-Übersetzungen
find locale/ -name "*.mo"

# Alle Übersetzungen (inkl. venv)
find . -name "*.mo" -not -path "*/venv/*" -not -path "*/__pycache__/*"
```

Die erste Suche sollte nur Dateien in `locale/` finden, wenn Sie `--locale` verwendet haben.
