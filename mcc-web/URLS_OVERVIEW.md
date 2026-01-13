# Aktuelle Browser-URLs für MyCyclingCity

## Übersicht

Die meisten URLs haben ein Sprach-Präfix (`/de/` oder `/en/`), außer den API-Endpunkten.

**Basis-URL:** `http://127.0.0.1:8000` (Development) oder Ihre Produktions-Domain

---

## Hauptanwendungen (mit Sprach-Präfix)

### Map App - Live-Karte
- `/{sprache}/map/` - Hauptansicht der Live-Karte
- `/{sprache}/map/kiosk/` - Kiosk-Modus der Karte
- `/{sprache}/map/kiosk/playlist/<uid>/` - Kiosk-Playlist für ein bestimmtes Gerät

**Map API-Endpunkte (ohne Sprach-Präfix):**
- `/api/map/api/group-avatars/` - Gruppen-Avatare für die Karte
- `/api/map/api/new-milestones/` - Neue Meilensteine
- `/api/map/api/all-milestones-status/` - Status aller Meilensteine

### Leaderboard App - High-Score Tiles
- `/{sprache}/leaderboard/` - Hauptansicht des Leaderboards
- `/{sprache}/leaderboard/kiosk/` - Kiosk-Modus des Leaderboards
- `/{sprache}/leaderboard/ticker/` - Ticker-Ansicht (Live-Updates)

### Ranking App - Ranglisten-Tabellen
- `/{sprache}/ranking/` - Hauptansicht der Ranglisten
- `/{sprache}/ranking/kiosk/` - Kiosk-Modus der Ranglisten

### Game App - Kilometer-Challenge
- `/{sprache}/game/` - Hauptansicht des Spiels

**Game API-Endpunkte (mit Sprach-Präfix):**
- `/{sprache}/game/api/game/cyclists` - Radler-Liste
- `/{sprache}/game/api/game/devices` - Geräte-Liste
- `/{sprache}/game/api/game/start` - Spiel starten
- `/{sprache}/game/api/game/data` - Spiel-Daten
- `/{sprache}/game/api/session/end` - Sitzung beenden
- `/{sprache}/game/api/sound/goal_reached` - Ziel-Sound
- `/{sprache}/game/api/game/images` - Spiel-Bilder

**Game HTMX-Endpunkte (mit Sprach-Präfix):**
- `/{sprache}/game/htmx/assignments` - Zuweisungen
- `/{sprache}/game/htmx/results` - Ergebnisse-Tabelle

### Django Admin
- `/{sprache}/admin/` - Django Admin-Interface

### Datenschutz
- `/{sprache}/privacy/` - Datenschutzerklärung

---

## API-Endpunkte (ohne Sprach-Präfix)

### Daten-Updates
- `/api/update-data` - Kilometer-Daten aktualisieren
- `/api/get-user-id` - Benutzer-ID abrufen

### Radler & Coins
- `/api/get-cyclist-coins/<username>` - Coins eines Radlers abrufen
- `/api/spend-cyclist-coins` - Coins ausgeben
- `/api/get-mapped-minecraft-cyclists` - Minecraft-Radler-Mapping

### Distanzen & Kilometer
- `/api/get-cyclist-distance/<identifier>` - Distanz eines Radlers
- `/api/get-group-distance/<identifier>` - Distanz einer Gruppe

### Leaderboard-APIs
- `/api/get-leaderboard/cyclists` - Radler-Leaderboard
- `/api/get-leaderboard/groups` - Gruppen-Leaderboard

### Aktive Radler
- `/api/get-active-cyclists` - Liste aktiver Radler

### Listen
- `/api/list-cyclists` - Liste aller Radler
- `/api/list-groups` - Liste aller Gruppen

### Meilensteine & Statistiken
- `/api/get-milestones` - Meilensteine abrufen
- `/api/get-statistics` - Statistiken abrufen
- `/api/get-travel-locations` - Reise-Orte abrufen

### Kiosk-Management
- `/api/kiosk/<uid>/playlist` - Playlist für Kiosk-Gerät abrufen
- `/api/kiosk/<uid>/commands` - Befehle für Kiosk-Gerät abrufen

### Geräte-Management
- `/api/device/config/report` - Geräte-Konfigurationsbericht
- `/api/device/config/fetch` - Geräte-Konfiguration abrufen
- `/api/device/firmware/download` - Firmware herunterladen
- `/api/device/firmware/info` - Firmware-Informationen
- `/api/device/heartbeat` - Geräte-Herzschlag

---

## Sprach-Switcher
- `/i18n/setlang/` - Sprache wechseln (POST-Request)

---

## Verfügbare Sprachen

Standardmäßig unterstützt:
- `/de/` - Deutsch (Standard)
- `/en/` - Englisch

---

## Beispiele für vollständige URLs

**Development:**
- `http://127.0.0.1:8000/de/map/` - Deutsche Karten-Ansicht
- `http://127.0.0.1:8000/en/leaderboard/` - Englisches Leaderboard
- `http://127.0.0.1:8000/de/ranking/` - Deutsche Ranglisten
- `http://127.0.0.1:8000/de/leaderboard/kiosk/` - Leaderboard im Kiosk-Modus
- `http://127.0.0.1:8000/api/update-data` - API-Endpunkt (ohne Sprach-Präfix)

**Produktion:**
Ersetzen Sie `http://127.0.0.1:8000` durch Ihre tatsächliche Domain.
