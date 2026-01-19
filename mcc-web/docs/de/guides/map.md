# Live-Karte - Benutzerhandbuch

## Übersicht

Die MyCyclingCity Live-Karte ist eine interaktive Kartenanwendung, die Echtzeit-Radaktivitäten anzeigt, einschließlich der Positionen aktiver Radler, Reise-Tracks, Meilensteine und Gruppenfortschritt. Die Karte verwendet OpenStreetMap (OSM) und Leaflet zur Visualisierung und aktualisiert sich automatisch alle 20 Sekunden.

## Inhaltsverzeichnis

- [Features](#features)
- [Erste Schritte](#erste-schritte)
- [Benutzeroberfläche](#benutzeroberflche)
- [Karten-Features](#karten-features)
- [Filterung und Ansichten](#filterung-und-ansichten)
- [Modi](#modi)
- [API Referenz](#api-referenz)
- [Tipps und Best Practices](#tipps-und-best-practices)
- [Fehlerbehebung](#fehlerbehebung)

## Features

### Kern-Funktionalität

- **Echtzeit-Tracking**: Live-Positionen aktiver Radler auf der Karte
- **Reise-Tracks**: Visuelle Darstellung von Radrouten (GPX-basiert)
- **Meilensteine**: Marker, die den Fortschritt entlang der Reise-Tracks zeigen
- **Gruppen-Avatare**: Visuelle Indikatoren für Gruppen auf der Karte
- **Auto-Update**: Automatische Aktualisierung alle 20 Sekunden
- **Mehrere Ansichten**: Gruppen-, Geräte- und Radler-Ansichten
- **Filterung**: Nach Gruppentyp filtern, nach Namen suchen
- **Mobile Unterstützung**: Optimierte Oberfläche für mobile Geräte
- **Kiosk-Modus**: Vollbild-Anzeigemodus für öffentliche Displays

### Karten-Elemente

- **Gruppen-Avatare**: Runde Marker, die Gruppenpositionen zeigen
- **Reise-Tracks**: Farbige Polylinien, die Radrouten zeigen
- **Meilensteine**: Flaggen-Marker, die Fortschrittspunkte anzeigen
- **Start/Ende-Marker**: Marker, die Track-Start- und Endpunkte zeigen
- **Aktive Radler**: Echtzeit-Positionsindikatoren

## Erste Schritte

### Zugriff auf die Karte

Navigieren Sie zu: `/{sprache}/map/` (z.B. `/de/map/` oder `/en/map/`)

### Erste Schritte

1. **Karte anzeigen**: Die Karte lädt automatisch mit allen aktiven Gruppen
2. **Tracks erkunden**: Klicken Sie auf Reise-Tracks, um Routendetails zu sehen
3. **Meilensteine prüfen**: Meilenstein-Marker entlang der Tracks anzeigen
4. **Gruppen filtern**: Verwenden Sie das Filter-Dropdown, um sich auf bestimmte Gruppen zu konzentrieren
5. **Ansichten wechseln**: Zwischen Gruppen-, Geräte- und Radler-Ansichten umschalten

## Benutzeroberfläche {#benutzeroberflche}

### Haupt-Kartenansicht

Die Kartenoberfläche besteht aus:

#### Kartenbereich

- **Interaktive Karte**: OSM-basierte Karte mit Zoom- und Pan-Steuerungen
- **Zoom-Steuerungen**: +/- Buttons in der oberen linken Ecke
- **Ebenen-Steuerung**: Sichtbarkeit von Routen und Tracks umschalten
- **Gruppen-Avatare**: Klickbare Marker, die Gruppenpositionen zeigen
- **Reise-Tracks**: Farbige Linien, die Radrouten zeigen

#### Steuerungs-Panel

Befindet sich auf der rechten Seite (Desktop) oder unten (Mobile):

- **Anzeigetyp-Auswahl**: Zwischen Gruppen, Geräten und Radlern wechseln
- **Gruppentyp-Filter**: Nach Gruppentyp filtern (z.B. Klassen, Teams)
- **Suchfeld**: Nach bestimmten Gruppen, Geräten oder Radlern suchen
- **Ansichts-Umschalter**: Zwischen Karten- und Tabellenansicht umschalten (Mobile)

#### Info-Panel

- **Gruppen-Informationen**: Details zu ausgewählten Gruppen
- **Distanz-Statistiken**: Gesamtkilometer und Session-Kilometer
- **Mitglieder-Listen**: Direkte und verschachtelte Gruppenmitglieder
- **Event-Informationen**: Aktive Events und Teilnehmer

### Mobile Oberfläche

Auf mobilen Geräten passt sich die Oberfläche an:

- **Vollbild-Karte**: Karte nimmt den gesamten Bildschirm ein
- **Unteres Panel**: Ausklappbares Panel mit Steuerungen und Informationen
- **Ansichts-Umschalter**: Button zum Umschalten zwischen Karten- und Tabellenansicht
- **Ebenen-Steuerung**: Ausklappbares Panel für Routensichtbarkeit
- **Touch-optimiert**: Optimiert für Touch-Interaktionen

### Kiosk-Modus

Für öffentliche Displays:

- **Vollbild-Anzeige**: Kein Browser-Chrome
- **Auto-Aktualisierung**: Kontinuierliche Updates
- **Große Schrift**: Aus der Entfernung lesbar
- **Minimale Steuerungen**: Vereinfachte Oberfläche

## Karten-Features

### Reise-Tracks

Reise-Tracks sind GPX-basierte Routen, die auf der Karte angezeigt werden:

- **Visualisierung**: Farbige Polylinien, die die Route zeigen
- **Start/Ende-Marker**: Klare Marker, die Track-Grenzen anzeigen
- **Gruppen-Zuordnung**: Tracks sind mit bestimmten Gruppen verknüpft
- **Fortschritts-Tracking**: Zeigt, wie weit Gruppen entlang der Tracks gereist sind

**Verwendung**:
1. Tracks werden automatisch angezeigt, wenn Gruppen aktiv sind
2. Klicken Sie auf einen Track, um Details zu sehen
3. Verwenden Sie die Ebenen-Steuerung, um bestimmte Tracks anzuzeigen/auszublenden
4. "Alle Routen" umschalten, um alle Tracks auf einmal anzuzeigen/auszublenden

### Meilensteine

Meilensteine markieren wichtige Punkte entlang der Reise-Tracks:

- **Visuelle Marker**: Flaggen-Icons auf der Karte
- **Fortschritts-Indikatoren**: Zeigen Gruppenfortschritt zu Zielen
- **Erfolgs-Tracking**: Aufzeichnung, wenn Gruppen Meilensteine erreichen
- **Popup-Benachrichtigungen**: Automatische Popups, wenn Meilensteine erreicht werden

**Verwendung**:
1. Meilensteine erscheinen automatisch entlang der Tracks
2. Klicken Sie auf einen Meilenstein-Marker, um Details zu sehen
3. Popups erscheinen, wenn Gruppen Meilensteine erreichen
4. Meilenstein-Status im Info-Panel prüfen

### Gruppen-Avatare

Gruppen-Avatare zeigen die aktuelle Position von Gruppen auf der Karte:

- **Positions-Marker**: Runde Marker mit Gruppen-Avataren
- **Echtzeit-Updates**: Positionen aktualisieren sich alle 20 Sekunden
- **Klickbar**: Klicken, um Gruppendetails zu sehen
- **Farbcodierung**: Verschiedene Farben für verschiedene Gruppentypen

**Verwendung**:
1. Avatare erscheinen automatisch für aktive Gruppen
2. Klicken Sie auf einen Avatar, um Gruppeninformationen zu sehen
3. Hover (Desktop), um schnelle Details zu sehen
4. Filtern, um nur bestimmte Gruppen anzuzeigen

### Aktive Radler

Echtzeit-Positions-Tracking für einzelne Radler:

- **Positions-Indikatoren**: Marker, die Radlerpositionen zeigen
- **Geräte-Zuordnung**: Verknüpft mit ESP32 Tachometer-Geräten
- **Live-Updates**: Positionen aktualisieren sich, wenn Daten empfangen werden
- **Session-Tracking**: Zeigt in der aktuellen Session zurückgelegte Distanz

## Filterung und Ansichten

### Anzeigetypen

Zwischen verschiedenen Ansichten wechseln:

#### Gruppen-Ansicht

- Zeigt alle Gruppen mit ihrer Hierarchie
- Zeigt Eltern- und Kind-Gruppen
- Zeigt Gesamtdistanz und Session-Distanz
- Nach Gruppentyp filtern

#### Geräte-Ansicht

- Listet alle aktiven ESP32-Geräte auf
- Zeigt Gerätenamen und Standorte
- Zeigt Gerätestatistiken
- Nach Gerätestatus filtern

#### Radler-Ansicht

- Listet alle aktiven Radler auf
- Zeigt individuelle Distanzen
- Zeigt Session-Kilometer
- Nach Radlernamen suchen

### Filteroptionen

#### Gruppentyp-Filter

Gruppen nach Typ filtern:
- "Alle" auswählen, um alle Gruppen anzuzeigen
- Bestimmten Gruppentyp wählen (z.B. "Klasse", "Team")
- Filter gilt für alle Ansichten

#### Suchfunktion

Nach bestimmten Elementen suchen:
- Namen in Suchfeld eingeben
- Ergebnisse filtern in Echtzeit
- Funktioniert in allen Ansichten
- Groß-/Kleinschreibung wird ignoriert

### URL-Parameter

Sie können die Kartenansicht mit URL-Parametern anpassen:

- `?group_id=123` - Bestimmte Gruppe nach ID anzeigen
- `?group_name=Klasse%201a` - Bestimmte Gruppe nach Namen anzeigen
- `?show_cyclists=false` - Radler aus Ansicht ausblenden
- `?interval=30` - Benutzerdefiniertes Aktualisierungsintervall (Sekunden) setzen

**Beispiel**:
```
/de/map/?group_id=5&interval=30
```

## Modi

### Standard-Modus

Standard-Modus für normale Benutzer:

- Vollständiges Steuerungs-Panel
- Alle Filteroptionen
- Interaktive Features
- Info-Panel sichtbar

### Mobile-Modus

Automatisch auf mobilen Geräten aktiviert:

- Touch-optimierte Oberfläche
- Ausklappbare Panels
- Vereinfachte Steuerungen
- Vollbild-Karten-Option

### Kiosk-Modus

Für öffentliche Displays:

- Vollbild-Anzeige
- Minimale Steuerungen
- Auto-Aktualisierung aktiviert
- Große, lesbare Schrift

Zugriff: `/{sprache}/map/kiosk/`

### Ticker-Modus

Scrollende Ticker-Ansicht für Displays:

- Kontinuierliches Scrollen
- Gruppen-Statistiken
- Event-Informationen
- Minimale Interaktion

Zugriff: `/{sprache}/map/ticker/`

## API Referenz

### Karten-API-Endpunkte

#### Gruppen-Avatare abrufen

**GET** `/api/map/api/group-avatars/`

Aktuelle Positionen und Avatare für alle Gruppen abrufen.

**Antwort**:
```json
{
  "groups": [
    {
      "id": 1,
      "name": "Klasse 1a",
      "avatar_url": "/media/avatars/class1a.png",
      "latitude": 52.52,
      "longitude": 13.405,
      "distance_total": 150.5,
      "current_track_id": 5
    }
  ]
}
```

#### Neue Meilensteine abrufen

**GET** `/api/map/api/new-milestones/`

Kürzlich erreichte Meilensteine abrufen.

**Antwort**:
```json
{
  "milestones": [
    {
      "id": 1,
      "name": "Berlin",
      "track_id": 5,
      "position_km": 100.0,
      "reached_by": ["Klasse 1a"],
      "reached_at": "2026-01-27T10:30:00Z"
    }
  ]
}
```

#### Alle Meilenstein-Status abrufen

**GET** `/api/map/api/all-milestones-status/`

Status aller Meilensteine für alle Tracks abrufen.

**Antwort**:
```json
{
  "tracks": [
    {
      "id": 5,
      "name": "Berlin nach Hamburg",
      "milestones": [
        {
          "id": 1,
          "name": "Berlin",
          "position_km": 0.0,
          "is_reached": true,
          "reached_by": ["Klasse 1a"]
        },
        {
          "id": 2,
          "name": "Hamburg",
          "position_km": 280.0,
          "is_reached": false,
          "reached_by": []
        }
      ]
    }
  ]
}
```

## Tipps und Best Practices

### Karten-Performance optimieren

1. **Filtern wenn möglich**: Verwenden Sie Filter, um die Anzahl der angezeigten Elemente zu reduzieren
2. **Ungenutzte Ebenen schließen**: Tracks ausblenden, die Sie nicht ansehen
3. **Aktualisierungsintervall anpassen**: Intervall für bessere Performance erhöhen
4. **Mobile-Modus verwenden**: Mobile-Modus ist für Performance optimiert

### Bestimmte Gruppen anzeigen

1. **URL-Parameter verwenden**: Bestimmte Gruppenansichten als Lesezeichen speichern
2. **Nach Typ filtern**: Auf relevante Gruppentypen eingrenzen
3. **Suchfunktion**: Schnell Gruppen nach Namen finden
4. **Mehrere Gruppen**: Komma-separierte IDs in URL verwenden

### Daten verstehen

1. **Gesamtdistanz**: Kumulative Distanz seit Start
2. **Session-Distanz**: Distanz in aktueller aktiver Session
3. **Track-Fortschritt**: Position entlang des Reise-Tracks in Kilometern
4. **Meilenstein-Status**: Prüfen, welche Meilensteine erreicht wurden

### Mobile Nutzung

1. **Vollbild-Modus**: Ansichts-Umschalter für Vollbild-Karte verwenden
2. **Ebenen-Steuerung**: Zugriff über Button oben rechts
3. **Tabellenansicht**: Für detaillierte Informationen zur Tabelle wechseln
4. **Touch-Gesten**: Pinch zum Zoomen, Ziehen zum Verschieben

## Fehlerbehebung

### Karte lädt nicht

**Symptome**: Leere Karte oder Fehlermeldung

**Lösungen**:
- Internetverbindung prüfen
- JavaScript aktiviert überprüfen
- Browser-Cache leeren
- Anderen Browser versuchen

### Keine Gruppen sichtbar

**Symptome**: Karte lädt, aber keine Gruppen angezeigt

**Lösungen**:
- Prüfen, ob Gruppen aktiv sind
- Gruppen-Sichtbarkeitseinstellungen überprüfen
- Filter entfernen, die Gruppen verstecken könnten
- Prüfen, ob Gruppen Geräte zugewiesen haben

### Positionen aktualisieren sich nicht

**Symptome**: Gruppenpositionen bleiben gleich

**Lösungen**:
- Auf nächste Auto-Aktualisierung warten (20 Sekunden)
- Seite manuell aktualisieren
- Prüfen, ob Geräte Daten senden
- Netzwerkverbindung überprüfen

### Meilensteine werden nicht angezeigt

**Symptome**: Keine Meilenstein-Marker auf der Karte

**Lösungen**:
- Überprüfen, ob Tracks Meilensteine konfiguriert haben
- Meilenstein-Sichtbarkeitseinstellungen prüfen
- Sicherstellen, dass Gruppen auf Tracks sind
- Ebenen-Sichtbarkeit prüfen

### Performance-Probleme

**Symptome**: Langsames Karten-Rendering oder Verzögerung

**Lösungen**:
- Anzahl sichtbarer Gruppen reduzieren
- Ungenutzte Tracks ausblenden
- Aktualisierungsintervall erhöhen
- Mobile-Modus für bessere Performance verwenden
- Andere Browser-Tabs schließen

### Mobile Anzeigeprobleme

**Symptome**: Karte füllt Bildschirm nicht oder Steuerungen versteckt

**Lösungen**:
- Gerät ins Querformat drehen
- Vollbild-Modus verwenden
- Browser-Zoom-Level prüfen
- Browser-Cache leeren
- Browser auf neueste Version aktualisieren

## Verwandte Dokumentation

- [Installations-Anleitung](../getting-started/installation.md)
- [Admin GUI Handbuch](../admin/index.md) - Tracks und Meilensteine konfigurieren
- [API Referenz](../api/index.md) - Vollständige API-Dokumentation
- [Spiel-Anleitung](game.md) - Kilometer-Challenge-System
