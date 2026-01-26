# Deployment-Anleitung

Diese Anleitung erklärt, wie Sie ein Deployment-Archiv erstellen und die MCC-Web-Anwendung in der Produktion bereitstellen.

## Übersicht

Der Deployment-Prozess besteht aus zwei Hauptschritten:

1. **Deployment-Archiv erstellen**: Alle notwendigen Dateien in ein tar.gz-Archiv packen
2. **In Produktion bereitstellen**: Das Produktionssystem initialisieren oder aktualisieren

## Schritt 1: Deployment-Archiv erstellen

Verwenden Sie `utils/create_deployment_archive.py`, um ein Deployment-Paket zu erstellen.

### Verwendung

```bash
# Grundlegende Verwendung (erstellt Archiv im Projektverzeichnis)
python utils/create_deployment_archive.py

# Ausgabeverzeichnis angeben
python utils/create_deployment_archive.py -o /pfad/zum/ausgabe

# Oder direkt ausführen
./utils/create_deployment_archive.py
```

### Was enthalten ist

Das Archiv enthält:
- Alle Python-Quelldateien
- Templates
- Statische Dateiquellen (nicht `staticfiles/` - wird auf dem Server generiert)
- Datenbank-Migrationen
- Übersetzungsdateien (`.po` Dateien)
- `requirements.txt`
- `manage.py`
- Konfigurationsdateien
- README und Dokumentation

### Was ausgeschlossen ist

Das Archiv schließt automatisch aus:
- `__pycache__/` Verzeichnisse
- `staticfiles/` (wird auf dem Server generiert)
- `media/` (benutzergenerierte Inhalte)
- Datenbankdateien (`data/db.sqlite3*`)
- Virtuelle Umgebungen
- IDE-Dateien
- Testdateien und Coverage-Reports
- Git-Repository

**Hinweis:** Kompilierte Übersetzungsdateien (`.mo`) im `locale/` Verzeichnis werden **eingeschlossen**, da sie in der Entwicklung kompiliert werden und in die Produktion bereitgestellt werden.

### Archiv-Benennung

Archive werden benannt: `mcc-web-deployment-{version}-{timestamp}.tar.gz`

Die Version wird bestimmt aus:
1. `version.txt` Datei (falls vorhanden)
2. Git-Tag/describe (Fallback)
3. "dev" (wenn keines verfügbar ist)

### version.txt generieren

Sie können `version.txt` automatisch generieren mit:

```bash
# Automatisch von Git erkennen
python utils/generate_version.py
# Oder mit make
make version

# Spezifische Version setzen
python utils/generate_version.py --version 1.2.3

# Aktuellen Git-Tag verwenden (wenn HEAD auf einem Tag ist)
python utils/generate_version.py --tag

# version.txt entfernen (Fallback zu git describe)
python utils/generate_version.py --clean
# Oder mit make
make version-clean
```

## Schritt 2: In Produktion bereitstellen

Verwenden Sie `utils/deploy_production.py`, um die Anwendung auf dem Produktionsserver bereitzustellen.

### Voraussetzungen

1. **Datenverzeichnisse in `/data/var/mcc` erstellen:**
   
   **Produktion:**
   Die folgenden Verzeichnisse müssen in `/data/var/mcc` angelegt werden:
   ```bash
   # Basisverzeichnis erstellen
   mkdir -p /data/var/mcc
   
   # Unterverzeichnisse erstellen
   mkdir -p /data/var/mcc/db          # Datenbank
   mkdir -p /data/var/mcc/logs       # Log-Dateien
   mkdir -p /data/var/mcc/tmp         # Temporäre Dateien (PID-Dateien)
   mkdir -p /data/var/mcc/staticfiles # Statische Dateien
   mkdir -p /data/var/mcc/media       # Media-Dateien (hochgeladene Inhalte)
   mkdir -p /data/var/mcc/backups    # Datenbank-Backups
   ```
   
   **Hinweis:** Die Verzeichnisse werden mit dem konfigurierten Benutzeraccount erstellt, der die Anwendung startet.

2. Das Deployment-Archiv auf dem Produktionsserver extrahieren

3. Python virtuelle Umgebung einrichten:
   
   **Produktion:**
   Das virtuelle Umgebung liegt außerhalb der Software in `/data/appl/mcc/venv`:
   ```bash
   # Falls noch nicht vorhanden, erstellen:
   python3 -m venv /data/appl/mcc/venv
   
   # Virtuelle Umgebung aktivieren:
   source /data/appl/mcc/venv/bin/activate
   
   # Pip aktualisieren (empfohlen):
   pip install --upgrade pip
   ```
   
   **Entwicklung:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
4. Abhängigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```

### Verwendung

```bash
# Vollständiges Deployment (empfohlen)
python utils/deploy_production.py

# Backup überspringen (nicht empfohlen für Produktion)
python utils/deploy_production.py --skip-backup

# Statische Dateien vor dem Sammeln löschen
python utils/deploy_production.py --clear-static

# Statische Dateien-Sammlung überspringen (wenn bereits durchgeführt)
python utils/deploy_production.py --skip-static

# Übersetzungskompilierung überspringen
python utils/deploy_production.py --skip-compilemessages
```

### Was das Script macht

Das Deployment-Script führt die folgenden Schritte in dieser Reihenfolge aus:

1. **Umgebungsprüfung**: Validiert die Django-Umgebung
2. **Datenbank-Backup**: Erstellt ein Backup der vorhandenen Datenbank (falls vorhanden)
   - Backups werden im `backups/` Verzeichnis gespeichert
   - Enthält Datenbankdatei und WAL/SHM-Dateien
   - Mit Zeitstempel: `db_backup_YYYYMMDD_HHMMSS.sqlite3`
3. **Datenbank-Migration**: Führt Django-Migrationen aus
   - Initialisiert die Datenbank, falls sie nicht existiert
   - Aktualisiert das Schema, falls die Datenbank existiert
4. **Statische Dateien**: Sammelt statische Dateien mit `collectstatic`
   - Erforderlich für Produktion (Apache bedient aus `staticfiles/`)
5. **Übersetzungen**: Verwendet bereits kompilierte Übersetzungsdateien (`.mo`) aus dem Archiv. Falls diese fehlen, werden sie als Fallback kompiliert (`.po` → `.mo`)
6. **Validierung**: Führt grundlegende Validierungsprüfungen durch

### Sicherheitsfunktionen

- **Automatisches Backup**: Datenbank wird vor jeder Migration gesichert
- **Fehlerbehandlung**: Script stoppt bei kritischen Fehlern
- **Validierung**: Prüfungen werden nach dem Deployment durchgeführt
- **Benutzerbestätigung**: Fordert Bestätigung an, wenn Backup fehlschlägt

### Befehlszeilen-Optionen

| Option | Beschreibung |
|--------|-------------|
| `--project-dir DIR` | Projektverzeichnis (Standard: aktuelles Verzeichnis) |
| `--skip-backup` | Datenbank-Backup überspringen (nicht empfohlen) |
| `--skip-static` | Statische Dateien-Sammlung überspringen |
| `--skip-compilemessages` | Übersetzungskompilierung überspringen |
| `--clear-static` | Vorhandene statische Dateien vor dem Sammeln löschen |
| `--fake-initial` | Initiale Migrationen als angewendet markieren, ohne sie auszuführen |

## Vollständiger Deployment-Workflow

### Auf dem Entwicklungsrechner

```bash
# 1. Deployment-Archiv erstellen
python utils/create_deployment_archive.py

# 2. Archiv auf Produktionsserver übertragen
scp mcc-web-deployment-*.tar.gz benutzer@produktions-server:/tmp/
```

### Auf dem Produktionsserver

**Wichtig:** Stellen Sie sicher, dass die virtuelle Umgebung bereits eingerichtet ist (siehe Voraussetzungen oben).

```bash
# 1. In das Basisverzeichnis wechseln
cd /data/appl/mcc

# 2. Archiv extrahieren (erstellt ein Verzeichnis wie mcc-web-1.2.3)
tar xzf /tmp/mcc-web-deployment-*.tar.gz

# 3. Symbolischen Link setzen, damit mcc-web auf die aktuelle Version zeigt
# (Alten Link entfernen, falls vorhanden)
rm -f mcc-web
ln -s mcc-web-* mcc-web

# 4. In das Anwendungsverzeichnis wechseln
cd mcc-web

# 5. Virtuelle Umgebung aktivieren (liegt außerhalb der Software)
source /data/appl/mcc/venv/bin/activate

# 6. Abhängigkeiten installieren/aktualisieren (falls nötig)
pip install -r requirements.txt

# 7. Deployment-Script ausführen
python utils/deploy_production.py

# 8. Anwendungsserver starten (Script)
/data/appl/mcc/mcc-web/scripts/mcc-web.sh start
```

## Wichtige Hinweise

### Datenbank-Backups

- Backups werden im `backups/` Verzeichnis im Projektverzeichnis gespeichert
- Mehrere Backups für Rollback-Fähigkeit behalten
- Automatische Backup-Rotation implementieren

### Statische Dateien

- Statische Dateien **müssen** auf dem Produktionsserver gesammelt werden
- Das `staticfiles/` Verzeichnis wird von Apache bedient, nicht von Django
- Verwenden Sie `--clear-static`, wenn Sie alte statische Dateien entfernen möchten

### Media-Dateien

- Das `media/` Verzeichnis enthält benutzergenerierte Inhalte
- **Niemals** `media/` während des Deployments überschreiben
- Sicherstellen, dass Media-Dateien separat gesichert werden

### Umgebungsvariablen

**Produktion:**
Die `.env` Datei liegt außerhalb der Software in `/data/appl/mcc/.env`

**Entwicklung:**
Die `.env` Datei kann im Projektverzeichnis (`mcc-web/.env`) oder individuell konfiguriert sein.

Stellen Sie sicher, dass diese Umgebungsvariablen gesetzt sind (über `.env` Datei oder System):

- `SECRET_KEY`: Django Secret Key
- `DEBUG`: Auf `False` für Produktion setzen
- `ALLOWED_HOSTS`: Komma-separierte Liste erlaubter Hostnamen
- `CSRF_TRUSTED_ORIGINS`: HTTPS-Origins für CSRF-Schutz
- Andere anwendungsspezifische Variablen (siehe `config/settings.py`)

**Hinweis:** In Entwicklungsumgebungen können die Pfade individuell sein, da die Anwendung relativ im Projektverzeichnis alle Informationen findet.

### Berechtigungen

Sicherstellen, dass die Dateiberechtigungen korrekt sind:
- Anwendungsdateien: lesbar für den konfigurierten Benutzer (der Benutzer, der die Anwendung startet)
- `media/` Verzeichnis: beschreibbar für den konfigurierten Benutzer
- Datenbankdatei: lesbar/beschreibbar für den konfigurierten Benutzer

**Hinweis:** Der Benutzer wird vom Admin konfiguriert und startet die Anwendung. Der Benutzer `mcc` ist nicht zwingend erforderlich.

## Fehlerbehebung

### Migration schlägt fehl

- Prüfen, ob Datenbank-Backup erstellt wurde
- Dateiberechtigungen für Datenbankdatei überprüfen
- Django-Logs auf spezifische Fehlermeldungen prüfen
- Bei Bedarf von Backup wiederherstellen

### Statische Dateien werden nicht aktualisiert

- `--clear-static` Flag verwenden, um Aktualisierung zu erzwingen
- `STATIC_ROOT` Einstellung in `config/settings.py` prüfen
- Apache-Konfiguration überprüfen, ob sie auf das korrekte `staticfiles/` Verzeichnis zeigt

### Übersetzungsprobleme

- Sicherstellen, dass `.po` Dateien im Archiv enthalten sind
- `compilemessages` bei Bedarf manuell ausführen: `python manage.py compilemessages`
- `LOCALE_PATHS` Einstellung prüfen

## Rollback-Verfahren

Wenn das Deployment fehlschlägt oder Probleme entdeckt werden:

1. **Anwendungsserver stoppen**
2. **Datenbank aus Backup wiederherstellen**:
   ```bash
   cp backups/db_backup_YYYYMMDD_HHMMSS.sqlite3 data/db.sqlite3
   ```
3. **Vorherige Code-Version wiederherstellen** (falls nötig)
4. **Anwendungsserver neu starten**

## Zusätzliche Ressourcen

- Django Deployment Checklist: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
- Projekt README: Siehe `README` Datei für zusätzliche Setup-Informationen
