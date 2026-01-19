# Kilometer-Challenge (Spiel) - Vollständige Anleitung

## Übersicht

Die Kilometer-Challenge ist ein Gamification-Feature von MyCyclingCity, das Benutzern ermöglicht, wettbewerbsfähige Herausforderungen zu erstellen, indem sie Radler Geräten zuordnen und ihren Fortschritt zu einer Zieldistanz verfolgen. Das System unterstützt sowohl Einzelspieler- als auch Mehrspieler-Modi mit Echtzeit-Synchronisation.

## Inhaltsverzeichnis

- [Features](#features)
- [Erste Schritte](#erste-schritte)
- [Benutzeroberfläche](#benutzeroberfläche)
- [Spiel-Modi](#spiel-modi)
- [API Referenz](#api-referenz)
- [Technische Details](#technische-details)
- [Best Practices](#best-practices)
- [Fehlerbehebung](#fehlerbehebung)

## Features

### Kern-Funktionalität

- **Geräte-Zuordnung**: Radler ESP32 Tachometer-Geräten zuordnen
- **Ziel-Setzung**: Optionale Zieldistanzen in Kilometern setzen
- **Echtzeit-Tracking**: Fortschritt mit Live-Updates überwachen
- **Coin-Berechnung**: Automatische Coin-Berechnung basierend auf Distanz
- **Gewinner-Erkennung**: Automatische Erkennung, wenn Ziele erreicht werden
- **Mehrspieler-Unterstützung**: Spiel-Räume für kollaborative Herausforderungen

### Einzelspieler-Modus

Im Einzelspieler-Modus können Benutzer:

- Radler Geräten zuordnen
- Eine Zieldistanz setzen (optional)
- Das Spiel starten, um Fortschritt zu verfolgen
- Echtzeit-Ergebnisse mit zurückgelegter Distanz und verdienten Coins anzeigen
- Das Spiel stoppen, um Ergebnisse einzufrieren
- Finale Statistiken anzeigen

### Mehrspieler-Modus (Spiel-Räume)

Spiel-Räume ermöglichen mehreren Spielern, an derselben Herausforderung teilzunehmen:

- **Raum-Erstellung**: Raum mit einem eindeutigen 8-stelligen Code erstellen
- **Raum-Beitritt**: Bestehenden Räumen beitreten, indem der Raum-Code eingegeben wird
- **QR-Code-Sharing**: QR-Codes für einfaches Raum-Sharing generieren
- **Master-System**: Der Raum-Ersteller wird zum "Master", der kann:
  - Ziel-Kilometer ändern
  - Alle Zuordnungen löschen
  - Master-Rolle an einen anderen Teilnehmer übertragen
  - Den Raum beenden
- **Echtzeit-Synchronisation**: Alle Teilnehmer sehen denselben Spiel-Status
- **Session-Management**: Automatisches Session-Tracking und Bereinigung

## Erste Schritte

### Voraussetzungen

- Aktive Radler im System
- Aktive Geräte (ESP32 Tachometer)
- Webbrowser mit aktiviertem JavaScript

### Zugriff auf das Spiel

Navigieren Sie zu: `/{sprache}/game/` (z.B. `/de/game/` oder `/en/game/`)

### Erste Schritte

1. **Radler auswählen**: Radler aus dem Dropdown-Menü wählen
2. **Geräte auswählen**: Verfügbare Geräte wählen
3. **Zuordnen**: Auf "Zuweisen" klicken, um Radler mit Geräten zu verknüpfen
4. **Ziel setzen** (Optional): Zieldistanz in Kilometern eingeben
5. **Spiel starten**: Auf "Spiel starten" klicken, um Tracking zu beginnen

## Benutzeroberfläche

### Haupt-Spiel-Seite

Die Spiel-Oberfläche besteht aus mehreren wichtigen Bereichen:

#### Zuordnungs-Bereich

- **Radler-Dropdown**: Aus verfügbaren Radlern auswählen
- **Geräte-Dropdown**: Aus verfügbaren Geräten auswählen
- **Zuordnen-Button**: Zuordnung zwischen Radler und Gerät erstellen
- **Zuordnungs-Liste**: Alle aktuellen Zuordnungen anzeigen
- **Entfernen-Button**: Einzelne Zuordnungen entfernen

#### Ziel-Bereich

- **Ziel-Eingabe**: Zieldistanz in Kilometern eingeben
- **Aktuelles Ziel-Anzeige**: Zeigt das aktuelle Ziel (falls gesetzt)
- **Ziel-Fortschritt**: Visueller Indikator des Fortschritts zum Ziel

#### Spiel-Steuerungen

- **Start-Button**: Tracking beginnen (nur sichtbar, wenn Spiel gestoppt ist)
- **Stop-Button**: Ergebnisse einfrieren (nur sichtbar, wenn Spiel läuft)
- **Spiel-Status**: Indikator, der zeigt, ob Spiel aktiv ist

#### Ergebnisse-Tabelle

Echtzeit-Tabelle, die zeigt:

- **Radler-Name**: Name des zugeordneten Radlers
- **Gerät**: Geräte-Identifikator
- **Start-Distanz**: Distanz beim Spielstart
- **Aktuelle Distanz**: Aktuelle Gesamtdistanz
- **Fortschritt**: Während des Spiels zurückgelegte Distanz
- **Coins**: Während des Spiels verdiente Coins
- **Status**: Gewinner-Indikator (falls Ziel erreicht)

#### Raum-Steuerungen (Mehrspieler)

- **Raum erstellen**: Neuen Spiel-Raum erstellen
- **Raum beitreten**: Raum-Code eingeben, um beizutreten
- **Raum-Code-Anzeige**: Zeigt aktuellen Raum-Code
- **Master-Steuerungen**: Zusätzliche Steuerungen für Raum-Master
- **Raum verlassen**: Aktuellen Raum verlassen

## Spiel-Modi

### Einzelspieler-Modus

**Anwendungsfall**: Individuelle Herausforderungen, Tests, Übung

**Workflow**:

1. Radler Geräten zuordnen
2. Ziel setzen (optional)
3. Spiel starten
4. Fortschritt überwachen
5. Spiel stoppen, wenn fertig

**Features**:

- Kein Raum-Code erforderlich
- Volle Kontrolle über Zuordnungen
- Kann jederzeit starten/stoppen
- Ergebnisse in Session gespeichert

### Mehrspieler-Modus (Spiel-Räume)

**Anwendungsfall**: Gruppen-Herausforderungen, Wettbewerbe, Klassenaktivitäten

**Workflow**:

1. Master erstellt Raum
2. Master teilt Raum-Code (oder QR-Code)
3. Teilnehmer treten Raum bei
4. Master setzt Ziel
5. Alle Teilnehmer ordnen Radler zu
6. Master startet Spiel
7. Alle Teilnehmer sehen synchronisierte Ergebnisse
8. Master stoppt Spiel, wenn fertig

**Features**:

- Synchronisierter Spiel-Status
- Master-Steuerungen
- QR-Code-Sharing
- Session-Tracking
- Automatische Bereinigung

## API Referenz

### HTMX-Endpunkte

Diese Endpunkte werden für Echtzeit-UI-Updates verwendet:

#### Zuordnungs-Verwaltung

**POST** `/{sprache}/game/htmx/assignments`

Radler-Geräte-Zuordnungen hinzufügen oder entfernen.

**Anfrage-Parameter**:
- `action`: `add` oder `remove`
- `cyclist_id`: Radler-Benutzer-ID
- `device_name`: Geräte-Identifikator

**Antwort**: HTML-Fragment mit aktualisierter Zuordnungs-Liste

#### Ergebnisse-Tabelle

**GET** `/{sprache}/game/htmx/results`

Aktuelle Ergebnisse-Tabelle abrufen.

**Antwort**: HTML-Fragment mit Ergebnisse-Tabelle

**Auto-Aktualisierung**: Alle 10 Sekunden, wenn Spiel aktiv ist

#### Ziel-Anzeige

**GET** `/{sprache}/game/htmx/target-km`

Aktuelle Ziel-Kilometer-Anzeige abrufen.

**Antwort**: HTML-Fragment mit Ziel-Informationen

**Auto-Aktualisierung**: Alle 3 Sekunden in Spiel-Räumen

#### Spiel-Buttons

**GET** `/{sprache}/game/htmx/game-buttons`

Spiel-Steuerungs-Buttons (Start/Stop) abrufen.

**Antwort**: HTML-Fragment mit Spiel-Buttons

#### Session-Synchronisation

**POST** `/{sprache}/game/htmx/sync-session`

Session mit Spiel-Raum synchronisieren.

**Anfrage-Parameter**:
- `room_code`: Raum-Code zum Synchronisieren

**Antwort**: JSON-Status

### REST API-Endpunkte

#### Spieler abrufen

**GET** `/{sprache}/game/api/game/cyclists`

Liste verfügbarer Radler für das Spiel abrufen.

**Antwort**:
```json
{
  "cyclists": [
    {
      "id": 1,
      "username": "MaxMustermann",
      "distance_total": 150.5,
      "coins_total": 300
    }
  ]
}
```

#### Spiel-Geräte abrufen

**GET** `/{sprache}/game/api/game/devices`

Liste verfügbarer Geräte abrufen.

**Antwort**:
```json
{
  "devices": [
    {
      "name": "MCC-Device_AB12",
      "display_name": "Gerät 1",
      "distance_total": 500.2
    }
  ]
}
```

#### Spiel starten/stoppen

**POST** `/{sprache}/game/api/game/start`

Spiel starten oder stoppen.

**Anfrage-Parameter**:
- `action`: `start` oder `stop`

**Antwort**:
```json
{
  "status": "game_started" // oder "game_stopped"
}
```

#### Spiel-Daten abrufen

**GET** `/{sprache}/game/api/game/data`

Aktuellen Spiel-Status und Statistiken abrufen.

**Antwort**:
```json
{
  "is_game_active": true,
  "is_game_stopped": false,
  "assignments": {
    "device1": "cyclist1"
  },
  "start_distances": {
    "cyclist1": 100.5
  },
  "current_distances": {
    "cyclist1": 150.2
  },
  "progress": {
    "cyclist1": 49.7
  },
  "coins": {
    "cyclist1": 99.4
  },
  "target_km": 200.0,
  "winners": []
}
```

#### Session beenden

**POST** `/{sprache}/game/api/session/end`

Aktuelle Spiel-Session beenden.

**Antwort**:
```json
{
  "status": "session_ended"
}
```

#### Ziel-erreicht-Sound

**GET** `/{sprache}/game/api/sound/goal_reached`

Gewinner-Sound-Datei abrufen.

**Antwort**: Audio-Datei (MP3/WAV)

#### Spiel-Bilder abrufen

**GET** `/{sprache}/game/api/game/images`

Spiel-bezogene Bilder abrufen.

**Antwort**: JSON mit Bild-URLs

### Raum-Verwaltungs-Endpunkte

#### Raum erstellen

**POST** `/{sprache}/game/room/create`

Neuen Spiel-Raum erstellen.

**Antwort**:
```json
{
  "room_code": "ABC123XY",
  "url": "/de/game/room/ABC123XY/"
}
```

#### Raum beitreten

**POST** `/{sprache}/game/room/join`

Bestehendem Spiel-Raum beitreten.

**Anfrage-Parameter**:
- `room_code`: 8-stelliger Raum-Code

**Antwort**: Weiterleitung zur Raum-Seite oder Fehler

#### Raum verlassen

**POST** `/{sprache}/game/room/leave`

Aktuellen Spiel-Raum verlassen.

**Antwort**: Weiterleitung zur Haupt-Spiel-Seite

#### Raum beenden

**POST** `/{sprache}/game/room/end`

Spiel-Raum beenden (nur Master).

**Antwort**: JSON-Status

#### Master übertragen

**POST** `/{sprache}/game/room/transfer-master`

Master-Rolle an einen anderen Teilnehmer übertragen.

**Anfrage-Parameter**:
- `target_cyclist_id`: Benutzer-ID des neuen Masters

**Antwort**: JSON-Status

#### QR-Code generieren

**GET** `/{sprache}/game/room/{room_code}/qr`

QR-Code für Raum-Sharing generieren.

**Antwort**: PNG-Bild mit QR-Code

## Technische Details

### Session-Management

Spiel-Status wird in Django-Sessions gespeichert:

- **Einzelspieler**: Status in Benutzer-Session gespeichert
- **Mehrspieler**: Status über `GameRoom`-Modell synchronisiert
- **Session-Keys**: Werden für Master-Identifikation verwendet
- **Ablauf**: Sessions laufen basierend auf Django-Einstellungen ab

### Datenfluss

1. **Zuordnung**: Benutzer ordnet Radler Gerät zu
   - Gespeichert in Session: `device_assignments`
   - Format: `{"device_name": "cyclist_user_id"}`

2. **Spiel-Start**: Benutzer klickt "Spiel starten"
   - Aktuelle Distanzen von `Cyclist.distance_total` abgerufen
   - Gespeichert in Session: `start_distances`
   - Format: `{"cyclist_user_id": start_distance}`

3. **Fortschritts-Berechnung**: Echtzeit-Updates
   - Aktuelle Distanz: `Cyclist.distance_total`
   - Fortschritt: `current_distance - start_distance`
   - Coins: `progress × coin_conversion_factor`

4. **Spiel-Stopp**: Benutzer klickt "Spiel stoppen"
   - Aktuelle Distanzen gespeichert: `stop_distances`
   - Ergebnisse eingefroren
   - Finale Statistiken berechnet

### HTMX-Integration

Das Spiel verwendet HTMX für Echtzeit-Updates ohne vollständige Seiten-Neuladung:

- **Ergebnisse-Tabelle**: Aktualisiert sich alle 10 Sekunden während aktivem Spiel
- **Ziel-Anzeige**: Aktualisiert sich alle 3 Sekunden in Räumen
- **Zuordnungs-Änderungen**: Lösen sofortige Tabellen-Aktualisierung aus
- **Spiel-Buttons**: Aktualisieren basierend auf Spiel-Status

### Raum-Code-Generierung

Raum-Codes sind 8-stellige alphanumerische Strings:

- **Zeichensatz**: Großbuchstaben und Zahlen
- **Ausgeschlossene Zeichen**: 0, O, I, 1 (um Verwechslungen zu vermeiden)
- **Eindeutigkeit**: Garantiert durch Datenbank-Constraint
- **Format**: `[A-Z2-9]{8}`

### Gewinner-Erkennung

Wenn ein Radler die Zieldistanz erreicht:

1. **Erkennung**: Wird bei jeder Ergebnisse-Tabellen-Aktualisierung geprüft
2. **Ankündigung**: Popup-Modal erscheint mit Gewinner-Informationen
3. **Sound**: Gewinner-Sound wird abgespielt
4. **Visuell**: Gewinner in Ergebnisse-Tabelle markiert
5. **Fortsetzung**: Spiel läuft weiter (kein Auto-Stopp)

### Modelle

#### GameRoom

Speichert gemeinsamen Spiel-Raum-Status:

```python
{
    "room_code": "ABC123XY",              # Eindeutiger 8-stelliger Code
    "master_session_key": "...",          # Session-Key des Masters
    "is_active": true,                    # Raum-Status
    "device_assignments": {               # Radler-Geräte-Zuordnungen
        "device1": "cyclist1",
        "device2": "cyclist2"
    },
    "start_distances": {                  # Distanzen beim Spielstart
        "cyclist1": 100.5,
        "cyclist2": 200.0
    },
    "stop_distances": {                   # Distanzen beim Spielstopp
        "cyclist1": 150.2,
        "cyclist2": 250.5
    },
    "is_game_stopped": false,             # Spiel-Status
    "announced_winners": [],              # Gewinner, die Ziel erreicht haben
    "current_target_km": 200.0,           # Aktuelles Ziel
    "active_sessions": [...],             # Aktive Session-Keys
    "session_to_cyclist": {...}          # Session-Radler-Zuordnung
}
```

#### GameSession

Verfolgt einzelne Spiel-Sessions (Django Session-Modell erweitert):

- Session-Key
- Raum-Code (falls im Raum)
- Ablaufdatum
- Spiel-Daten

## Berechtigungen

### Master-Berechtigungen

Der Raum-Ersteller (Master) kann:

- Ziel-Kilometer ändern
- Alle Zuordnungen löschen
- Master-Rolle an einen anderen Teilnehmer übertragen
- Den Raum beenden
- Spiel starten/stoppen

### Teilnehmer-Berechtigungen

Reguläre Teilnehmer können:

- Eigene Zuordnungen hinzufügen/entfernen
- Spiel-Status anzeigen
- Den Raum verlassen
- Ergebnisse anzeigen

## Best Practices

### Spiel einrichten

1. **Radler vorbereiten**: Sicherstellen, dass alle Radler registriert sind
2. **Geräte vorbereiten**: Überprüfen, dass Geräte aktiv sind und Daten senden
3. **Klare Ziele setzen**: Zieldistanzen vor dem Start definieren
4. **Zuordnungen testen**: Überprüfen, dass Zuordnungen korrekt funktionieren
5. **Regeln kommunizieren**: Spielregeln den Teilnehmern erklären

### Mehrspieler-Spiele durchführen

1. **Raum früh erstellen**: Raum erstellen, bevor Teilnehmer ankommen
2. **Code klar teilen**: Raum-Code prominent anzeigen
3. **QR-Codes verwenden**: QR-Codes für einfaches Beitreten generieren
4. **Fortschritt überwachen**: Ergebnisse-Tabelle regelmäßig prüfen
5. **Master-Rolle verwalten**: Übertragen, wenn Ersteller geht
6. **Aufräumen**: Räume beenden, wenn fertig

### Performance-Optimierung

1. **Teilnehmer begrenzen**: Raumgröße angemessen halten (< 50 Teilnehmer)
2. **Sessions überwachen**: Abgelaufene Sessions regelmäßig bereinigen
3. **Datenbank-Indizierung**: Sicherstellen, dass richtige Indizes auf GameRoom-Feldern vorhanden sind
4. **HTMX-Caching**: Angemessene Cache-Header verwenden

## Fehlerbehebung

### Raum nicht gefunden

**Symptome**: Fehler beim Beitreten zum Raum

**Lösungen**:
- Überprüfen, dass der 8-stellige Code korrekt ist
- Prüfen, ob der Raum beendet wurde
- Sicherstellen, dass das korrekte URL-Format verwendet wird
- Überprüfen, dass Raum noch aktiv ist

### Synchronisations-Probleme

**Symptome**: Teilnehmer sehen unterschiedliche Spiel-Status

**Lösungen**:
- Seite aktualisieren, um erneut zu synchronisieren
- Prüfen, ob Sie noch im Raum sind (nach Raum-Code-Anzeige suchen)
- Überprüfen, dass Ihre Session aktiv ist
- Netzwerkverbindung prüfen

### Master-Übertragung schlägt fehl

**Symptome**: Master-Rolle kann nicht übertragen werden

**Lösungen**:
- Sicherstellen, dass Ziel-Radler eine Zuordnung hat
- Prüfen, dass Radler in der `session_to_cyclist`-Zuordnung ist
- Überprüfen, dass Raum noch aktiv ist
- Sicherstellen, dass Sie der aktuelle Master sind

### Spiel startet nicht

**Symptome**: Start-Button funktioniert nicht

**Lösungen**:
- Überprüfen, dass mindestens eine Zuordnung existiert
- Browser-Konsole auf Fehler prüfen
- Sicherstellen, dass Session gültig ist
- In Räumen: Überprüfen, dass Sie der Master sind

### Ergebnisse aktualisieren sich nicht

**Symptome**: Ergebnisse-Tabelle zeigt alte Daten

**Lösungen**:
- Prüfen, dass HTMX funktioniert (Browser-Konsole)
- Überprüfen, dass Spiel aktiv ist
- Seite aktualisieren
- Netzwerk-Anfragen in Browser-Entwicklertools prüfen

### Zuordnungs-Probleme

**Symptome**: Radler kann nicht Gerät zugeordnet werden

**Lösungen**:
- Überprüfen, dass Radler existiert und aktiv ist
- Prüfen, dass Gerät verfügbar ist
- Sicherstellen, dass keine doppelten Zuordnungen existieren
- Browser-Konsole auf Fehler prüfen

## Zukünftige Verbesserungen

Geplante potenzielle Verbesserungen:

- **Team-basierte Herausforderungen**: Radler in Teams gruppieren
- **Historische Statistiken**: Spiel-Verlauf und Statistiken verfolgen
- **Erfolgs-System**: Abzeichen und Erfolge
- **Benutzerdefinierte Spiel-Modi**: Verschiedene Spiel-Typen
- **Leaderboard-Integration**: Verknüpfung mit Haupt-Leaderboard
- **Ergebnisse exportieren**: Spiel-Ergebnisse als CSV/PDF herunterladen
- **Wiederholungs-Modus**: Vergangene Spiele überprüfen
- **Turnier-System**: Mehrrunden-Wettbewerbe

## Verwandte Dokumentation

- [Installations-Anleitung](../getting-started/installation.md)
- [Admin GUI Handbuch](../admin/index.md) - Spiel-Räume und Sessions verwalten
- [API Referenz](../api/index.md) - Vollständige API-Dokumentation
