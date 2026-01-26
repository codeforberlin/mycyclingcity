# Installations-Anleitung

Diese Anleitung erklärt, wie Sie die MyCyclingCity Entwicklungsumgebung einrichten.

## Voraussetzungen

- Python 3.11 oder höher
- pip (Python Package Manager)
- Git
- Virtuelle Umgebung (empfohlen)

## Schritt 1: Repository klonen

```bash
git clone https://github.com/codeforberlin/mycyclingcity.git
cd mycyclingcity
```

## Schritt 2: Python Virtuelle Umgebung einrichten

### Option A: Projekt-lokale Virtuelle Umgebung (Empfohlen)

```bash
cd mcc-web
python3 -m venv venv
source venv/bin/activate  # Unter Windows: venv\Scripts\activate
```

### Option B: Externe Virtuelle Umgebung

Für Entwicklung auf verschiedenen Systemen mit unterschiedlichen Python-Installationen (z.B. NAS-Server):

```bash
# Virtuelle Umgebung im Home-Verzeichnis erstellen
python3 -m venv ~/venv_mcc
source ~/venv_mcc/bin/activate
```

## Schritt 3: Abhängigkeiten installieren

```bash
cd mcc-web
pip install --upgrade pip
pip install -r requirements.txt
```

### Erforderliche Pakete

- Django==5.2.9
- requests==2.32.5
- gunicorn==23.0.0
- gpxpy==1.6.2
- pillow==12.0.0
- python-decouple==3.8
- python-dotenv==1.0.0
- pytest==8.0.0
- pytest-django==4.8.0
- factory-boy==3.3.0
- qrcode[pil]==7.4.2

## Schritt 4: Umgebungsvariablen konfigurieren

**Entwicklung:**
Erstellen Sie eine `.env` Datei im `mcc-web/` Verzeichnis:

```bash
cp .env.example .env  # Falls Beispiel vorhanden
# Oder manuell erstellen
```

**Produktion:**
Die `.env` Datei liegt außerhalb der Software in `/data/appl/mcc/.env`

Mindestens erforderliche Variablen:

```env
SECRET_KEY=ihr-geheimer-schlüssel-hier
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

**Hinweis:** In Entwicklungsumgebungen kann die `.env` Datei individuell konfiguriert sein, da die Anwendung relativ im Projektverzeichnis alle Informationen findet.

## Schritt 5: Datenbank-Migrationen ausführen

```bash
python manage.py migrate
```

## Schritt 6: Superuser erstellen (Optional)

```bash
python manage.py createsuperuser
```

## Schritt 7: Statische Dateien sammeln

```bash
python manage.py collectstatic
```

## Schritt 8: Entwicklungsserver starten

```bash
python manage.py runserver
```

Zugriff auf die Anwendung:
- Admin: http://127.0.0.1:8000/admin
- Spiel: http://127.0.0.1:8000/de/game/
- Karte: http://127.0.0.1:8000/de/map/

## Überprüfung

Um die Installation zu überprüfen:

1. Prüfen Sie, dass der Server ohne Fehler startet
2. Zugriff auf das Admin-Interface unter `/admin`
3. Tests ausführen: `pytest api/tests/`

## Fehlerbehebung

### Import-Fehler

- Stellen Sie sicher, dass die virtuelle Umgebung aktiviert ist
- Überprüfen Sie, dass alle Abhängigkeiten installiert sind: `pip list`
- Prüfen Sie die Python-Version: `python --version` (sollte 3.11+ sein)

### Datenbank-Fehler

- Stellen Sie sicher, dass SQLite verfügbar ist (in Python enthalten)
- Prüfen Sie die Dateiberechtigungen für `data/db.sqlite3`
- Migrationen ausführen: `python manage.py migrate`

### Statische Dateien werden nicht geladen

- Führen Sie `python manage.py collectstatic` aus
- Prüfen Sie `STATIC_ROOT` in `config/settings.py`
- Überprüfen Sie `DEBUG=True` in der Entwicklung

## Nächste Schritte

- [Konfigurations-Anleitung](configuration.md) - Anwendung konfigurieren
- [Admin GUI Handbuch](../admin/index.md) - Admin-Interface verwenden lernen
- [API Referenz](../api/index.md) - API erkunden
