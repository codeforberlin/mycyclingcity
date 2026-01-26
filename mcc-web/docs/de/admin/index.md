# Admin GUI Handbuch

Dieses Handbuch erklärt, wie Sie das Django Admin Interface zur Verwaltung von MyCyclingCity verwenden.

## Zugriff auf das Admin Interface

1. Navigieren Sie zu: `http://ihre-domain/admin/`
2. Melden Sie sich mit Ihren Superuser-Anmeldedaten an
3. Sie sehen das Admin-Dashboard mit allen verfügbaren Modellen

## Hauptbereiche

Das Admin Interface ist in folgende Bereiche organisiert:

### MCC Core API & Models

Kern-Funktionalität für Radler, Gruppen und Kilometer-Tracking.

#### Gruppentypen

- **Zweck**: Definieren Sie Typen von Gruppen (z.B. Klassen, Teams)
- **Wichtige Felder**:
  - `name`: Gruppentyp-Name
  - `description`: Beschreibung des Gruppentyps
  - `is_active`: Gruppentyp aktivieren/deaktivieren
- **Verwendung**: Erstellen Sie Gruppentypen, bevor Sie Gruppen erstellen

#### Gruppen

- **Zweck**: Radgruppen verwalten (Klassen, Teams, etc.)
- **Wichtige Felder**:
  - `name`: Gruppenname
  - `group_type`: Typ der Gruppe
  - `school_name`: Zugeordnete Schule
  - `distance_total`: Gesamt zurückgelegte Kilometer
  - `is_active`: Aktiv-Status
- **Features**:
  - Aggregierte Kilometer anzeigen
  - Gruppenfortschritt verfolgen
  - Gruppenhierarchie verwalten (Eltern-/Kind-Gruppen)

#### Radler

- **Zweck**: Einzelne Radler verwalten
- **Wichtige Felder**:
  - `user`: Zugeordneter Django-Benutzer
  - `id_tag`: RFID-Tag-Identifikator
  - `coin_conversion_factor`: Coins pro Kilometer
  - `distance_total`: Gesamtkilometer
  - `coins_total`: Gesamt verdiente Coins
- **Features**:
  - Radler mit Benutzern verknüpfen
  - Coin-Umrechnung konfigurieren
  - Radstatistiken anzeigen

#### Reise-Tracks

- **Zweck**: Reiserouten und Tracks verwalten
- **Wichtige Felder**:
  - `name`: Track-Name
  - `gpx_file`: GPX-Routendatei
  - `distance_km`: Track-Distanz
  - `milestones`: Zugeordnete Meilensteine
- **Verwendung**: GPX-Dateien hochladen, um Reise-Tracks zu erstellen

#### Meilensteine

- **Zweck**: Meilensteine entlang von Reise-Tracks definieren
- **Wichtige Felder**:
  - `name`: Meilenstein-Name
  - `travel_track`: Zugeordneter Track
  - `position_km`: Position auf dem Track
  - `is_locked`: Sperr-Status
- **Features**:
  - Gruppenfortschritt zu Meilensteinen verfolgen
  - Erfolge vergeben

#### Events

- **Zweck**: Rad-Events verwalten
- **Wichtige Felder**:
  - `name`: Event-Name
  - `start_date`: Event-Start
  - `end_date`: Event-Ende
  - `groups`: Teilnehmende Gruppen
- **Verwendung**: Rad-Events erstellen und verwalten

### IoT Management

Geräte- und Firmware-Verwaltung für ESP32-Geräte.

#### Geräte

- **Zweck**: ESP32 Tachometer-Geräte verwalten
- **Wichtige Felder**:
  - `name`: Geräte-Identifikator
  - `display_name`: Menschenlesbarer Name
  - `group`: Zugeordnete Gruppe
  - `distance_total`: Gesamt-Gerätekilometer
  - `last_active`: Zeitstempel der letzten Aktivität
- **Features**:
  - Gerätestatus überwachen
  - Gerätestatistiken anzeigen
  - Geräteeinstellungen konfigurieren

#### Geräte-Konfigurationen

- **Zweck**: Server-seitige Geräte-Konfiguration
- **Wichtige Felder**:
  - `device`: Zugeordnetes Gerät
  - `device_specific_api_key`: Geräte-API-Key
  - `send_interval_seconds`: Datenübertragungsintervall
  - `wheel_size`: Radumfang
- **Features**:
  - Geräteparameter remote konfigurieren
  - API-Key-Verwaltung
  - Konfigurationssynchronisation

#### Firmware-Images

- **Zweck**: Firmware-Versionen für OTA-Updates verwalten
- **Wichtige Felder**:
  - `version`: Firmware-Version
  - `file`: Firmware-Binary
  - `is_active`: Aktive Version
  - `release_notes`: Versionshinweise
- **Verwendung**: Firmware für automatische Geräte-Updates hochladen

#### Geräte-Gesundheit

- **Zweck**: Geräte-Gesundheitsstatus überwachen
- **Wichtige Felder**:
  - `device`: Zugeordnetes Gerät
  - `status`: Gesundheitsstatus (online/offline/warnung/fehler)
  - `last_heartbeat`: Zeitstempel des letzten Heartbeats
  - `consecutive_failures`: Fehleranzahl
- **Features**:
  - Echtzeit-Geräteüberwachung
  - Gesundheitsstatus-Tracking
  - Fehlerberichterstattung

### MCC Game Interface

Spiel-Raum- und Session-Verwaltung.

#### Spiel-Räume

- **Zweck**: Multiplayer-Spiel-Räume verwalten
- **Wichtige Felder**:
  - `room_code`: Eindeutiger Raum-Identifikator
  - `is_active`: Raum-Status
  - `master_session_key`: Master-Session
  - `device_assignments`: Radler-Geräte-Zuordnungen
- **Features**:
  - Aktive Spiel-Räume anzeigen
  - Raumaktivität überwachen
  - Raumstatus verwalten

#### Spiel-Sessions

- **Zweck**: Einzelne Spiel-Sessions verfolgen
- **Wichtige Felder**:
  - `session_key`: Session-Identifikator
  - `room_code`: Zugeordneter Raum
  - `expire_date`: Session-Ablauf
- **Features**:
  - Aktive Sessions überwachen
  - Abgelaufene Sessions bereinigen
  - Spielstatus debuggen

### Kiosk Management

Kiosk-Geräte- und Playlist-Verwaltung.

#### Kiosk-Geräte

- **Zweck**: Kiosk-Anzeigegeräte verwalten
- **Wichtige Felder**:
  - `uid`: Eindeutiger Geräte-Identifikator
  - `name`: Gerätename
  - `is_active`: Aktiv-Status
- **Verwendung**: Kiosk-Anzeigen konfigurieren

### Management (Mgmt)

System-Verwaltung und Monitoring-Funktionen.

#### Server Control

- **Zweck**: Gunicorn-Server steuern (Start, Stop, Restart, Reload)
- **Zugriff**: `/admin/server/`
- **Features**:
  - Server-Status anzeigen
  - Server starten/stoppen/neu starten
  - Konfiguration neu laden (ohne Neustart)
  - Server-Metriken anzeigen
  - Health-Checks durchführen
- **Verwendung**: Nur für Superuser verfügbar

#### Log File Viewer

- **Zweck**: Anwendungs-Logdateien direkt im Admin GUI anzeigen
- **Zugriff**: `/admin/logs/`
- **Features**:
  - Logdateien durchsuchen und filtern
  - Nach Log-Level filtern (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Suche in Logs
  - Rotierte Logdateien anzeigen
  - Auto-Refresh für Live-Ansicht
  - Beliebige Logdateien aus `logs/` Verzeichnis auswählen
- **Verfügbare Logs**:
  - API Application Logs (`api.log`)
  - Management Application Logs (`mgmt.log`)
  - IoT Application Logs (`iot.log`)
  - Kiosk Application Logs (`kiosk.log`)
  - Game Application Logs (`game.log`)
  - Map Application Logs (`map.log`)
  - Leaderboard Application Logs (`leaderboard.log`)
  - Django Framework Logs (`django.log`)

#### Backup Management

- **Zweck**: Datenbank-Backups verwalten
- **Zugriff**: `/admin/backup/`
- **Features**:
  - Backups erstellen
  - Backup-Liste anzeigen (mit Größe und Datum)
  - Backups herunterladen
  - Backup-Verwaltung
- **Verwendung**: Backups werden in `backups/` Verzeichnis gespeichert

#### Gunicorn Configuration

- **Zweck**: Gunicorn-Server-Konfiguration über Admin GUI
- **Zugriff**: `/admin/mgmt/gunicornconfig/`
- **Wichtige Einstellungen**:
  - `log_level`: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - `workers`: Anzahl Worker-Prozesse (0 = automatisch)
  - `threads`: Threads pro Worker
  - `worker_class`: Worker-Klasse (gthread, sync)
  - `bind`: Bind-Adresse und Port
- **Features**:
  - Konfiguration ohne Environment-Variablen ändern
  - Server-Neustart erforderlich nach Änderungen
  - Link zu Server Control für Neustart

#### Logging Configuration

- **Zweck**: Anwendungs-Logging konfigurieren
- **Zugriff**: `/admin/mgmt/loggingconfig/`
- **Features**:
  - Log-Level pro Logger konfigurieren
  - Logging zu Datenbank aktivieren/deaktivieren
  - DEBUG/INFO Logs in Datenbank aktivieren
  - Request-Logging aktivieren/deaktivieren

#### Performance Monitoring

- **Zweck**: System-Performance überwachen
- **Modelle**:
  - **Request Logs**: HTTP-Request-Logs mit Performance-Daten
  - **Performance Metrics**: Aggregierte Performance-Metriken
  - **Alert Rules**: Regeln für Performance-Alerts
- **Features**:
  - Request-Zeiten analysieren
  - Langsame Requests identifizieren
  - Performance-Trends verfolgen

#### Minecraft Control

- **Zweck**: Minecraft-Server steuern und Coin-Synchronisation verwalten
- **Zugriff**: `/admin/minecraft/`
- **Features**:
  - Bridge-Worker starten/stoppen (Coin-Synchronisation)
  - Snapshot-Worker starten/stoppen (Status-Erfassung)
  - Manuelle Synchronisation aller Spieler
  - Scoreboard-Snapshot aktualisieren
  - RCON-Verbindung testen
  - Outbox-Events verwalten
  - Player-Liste mit Coin-Status anzeigen
- **Dokumentation**: Siehe [Minecraft-Integration Dokumentation](minecraft.md)

### Historical Reports & Analytics

Historische Berichte und Analysen.

#### Analytics Dashboard

- **Zweck**: Historische Daten analysieren und Berichte erstellen
- **Zugriff**: `/admin/analytics/`
- **Features**:
  - Zeitreihen-Analysen
  - Gruppen-Vergleiche
  - Export-Funktionen
  - Hierarchie-Breakdown

#### Hierarchy Breakdown

- **Zweck**: Detaillierte Hierarchie-Analysen
- **Zugriff**: `/admin/analytics/hierarchy/`
- **Features**:
  - Gruppen-Hierarchie visualisieren
  - Detaillierte Statistiken pro Ebene

### Session Management

Spiel-Session-Verwaltung und Debugging.

#### Session Dashboard

- **Zweck**: Aktive Spiel-Sessions überwachen und verwalten
- **Zugriff**: `/admin/game/session/dashboard/`
- **Features**:
  - Aktive Sessions anzeigen
  - Session-Daten bearbeiten
  - Sessions in Räumen verwalten
  - Master-Sessions verwalten
  - Session-Daten als JSON exportieren

## Häufige Aufgaben

### Neuen Radler erstellen

1. Navigieren Sie zu **MCC Core API & Models** → **Radler**
2. Klicken Sie auf **Radler hinzufügen**
3. Füllen Sie die erforderlichen Felder aus:
   - `user`: Django-Benutzer auswählen oder erstellen
   - `id_tag`: RFID-Tag-ID eingeben
   - `coin_conversion_factor`: Coins pro Kilometer setzen
4. Klicken Sie auf **Speichern**

### Gerät einer Gruppe zuordnen

1. Navigieren Sie zu **IoT Management** → **Geräte**
2. Wählen Sie das Gerät aus
3. Wählen Sie im Feld **Gruppe** die Zielgruppe aus
4. Klicken Sie auf **Speichern**

### Firmware hochladen

1. Navigieren Sie zu **IoT Management** → **Firmware Images**
2. Klicken Sie auf **Firmware Image hinzufügen**
3. Füllen Sie aus:
   - `version`: Versionsnummer (z.B. "1.2.3")
   - `file`: Firmware-Binary (.bin) hochladen
   - `is_active`: Aktivieren, wenn dies die aktive Version ist
   - `release_notes`: Änderungen beschreiben
4. Klicken Sie auf **Speichern**

### Geräteeinstellungen konfigurieren

1. Navigieren Sie zu **IoT Management** → **Device Configurations**
2. Wählen Sie oder erstellen Sie eine Konfiguration für ein Gerät
3. Konfigurieren Sie:
   - `send_interval_seconds`: Wie oft das Gerät Daten sendet
   - `wheel_size`: Radumfang in cm
   - `device_specific_api_key`: Geräte-Authentifizierungsschlüssel
4. Klicken Sie auf **Speichern**

### Geräte-Gesundheit anzeigen

1. Navigieren Sie zu **IoT Management** → **Device Health**
2. Status für alle Geräte anzeigen:
   - **Grün**: Online und gesund
   - **Gelb**: Warnung (keine kürzliche Aktivität)
   - **Rot**: Fehler oder offline
3. Klicken Sie auf ein Gerät, um detaillierte Gesundheitsinformationen zu sehen

### Spiel-Räume verwalten

1. Navigieren Sie zu **MCC Game Interface** → **Game Rooms**
2. Alle aktiven und inaktiven Räume anzeigen
3. Klicken Sie auf einen Raum, um:
   - Raumstatus anzuzeigen
   - Teilnehmer zu sehen
   - Spielfortschritt zu überwachen
   - Raum zu beenden, falls nötig

## Erweiterte Features

### Bulk-Aktionen

Viele Admin-Seiten unterstützen Bulk-Aktionen:
1. Mehrere Elemente mit Checkboxen auswählen
2. Eine Aktion aus dem Dropdown wählen
3. Auf **Los** klicken

### Filterung und Suche

- **Listen-Filter**: Verwenden Sie Seitenleisten-Filter, um Ergebnisse einzugrenzen
- **Suche**: Verwenden Sie Suchfelder, um bestimmte Elemente zu finden
- **Datumshierarchie**: Klicken Sie auf Datumslinks, um nach Zeitraum zu filtern

### Inline-Bearbeitung

Einige Modelle unterstützen Inline-Bearbeitung:
- Verwandte Objekte direkt vom übergeordneten Objekt aus bearbeiten
- Neue verwandte Objekte hinzufügen, ohne die Seite zu verlassen

### Benutzerdefinierte Aktionen

Einige Modelle haben benutzerdefinierte Admin-Aktionen:
- **Sessions löschen**: Spiel-Sessions in Bulk löschen
- **Daten exportieren**: Modelldaten nach CSV/JSON exportieren
- **Bereinigung**: Abgelaufene oder verwaiste Datensätze entfernen

## Best Practices

1. **Regelmäßige Backups**: Immer vor Bulk-Operationen sichern
2. **Änderungen testen**: Konfigurationsänderungen zuerst auf einem Entwicklungssystem testen
3. **Gesundheit überwachen**: Regelmäßig den Device Health Status prüfen
4. **Bereinigung**: Periodisch abgelaufene Sessions und alte Daten bereinigen
5. **Dokumentation**: Benutzerdefinierte Konfigurationen und Änderungen dokumentieren

## Fehlerbehebung

### Kein Zugriff auf Admin

- Überprüfen Sie, dass Sie als Superuser angemeldet sind
- Prüfen Sie `ALLOWED_HOSTS` in den Einstellungen
- Stellen Sie sicher, dass `DEBUG=True` in der Entwicklung

### Änderungen werden nicht gespeichert

- Prüfen Sie auf Validierungsfehler (roter Text)
- Überprüfen Sie, dass erforderliche Felder ausgefüllt sind
- Prüfen Sie Datenbankberechtigungen

### Gerät erscheint nicht

- Überprüfen Sie, dass das Gerät in Geräte registriert ist
- Prüfen Sie den Device Health Status
- Stellen Sie sicher, dass das Gerät mindestens einen Heartbeat gesendet hat

## Verwandte Dokumentation

- [Installations-Anleitung](../getting-started/installation.md)
- [Konfigurations-Anleitung](../getting-started/configuration.md)
- [API Referenz](../api/index.md)
