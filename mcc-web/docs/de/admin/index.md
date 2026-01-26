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

### Historische Berichte & Analysen

Analysen und Berichte für historische Daten.

#### Analytics Dashboard

- **Zweck**: Übersichtliche Darstellung von Analysen und Statistiken
- **Features**:
  - Gruppenstatistiken
  - Kilometer-Trends
  - Zeitraum-Analysen
  - Export-Funktionen
- **Zugriff**: `/admin/analytics/`

#### Hierarchy Breakdown

- **Zweck**: Detaillierte Aufschlüsselung der Gruppenhierarchie
- **Features**:
  - Hierarchische Darstellung von Gruppen
  - Aggregierte Statistiken pro Ebene
  - Drill-Down-Funktionalität
- **Zugriff**: `/admin/analytics/hierarchy/`

### Session Management

Spiel-Session-Verwaltung und Monitoring.

#### Session Dashboard

- **Zweck**: Übersicht über aktive und vergangene Spiel-Sessions
- **Features**:
  - Aktive Sessions anzeigen
  - Session-Status überwachen
  - Session-Details einsehen
  - Session-Verwaltung
- **Zugriff**: `/admin/game/session/dashboard/`

### Mgmt (Verwaltung)

Server-Verwaltung und System-Monitoring.

#### Server Control

- **Zweck**: Server-Status und -Steuerung
- **Features**:
  - Server-Status anzeigen (laufend/gestoppt)
  - Server starten, stoppen, neustarten
  - Server-Metriken anzeigen
  - Health-Check-Status
  - Gunicorn-Konfiguration anzeigen
- **Zugriff**: `/admin/server/` oder über "Mgmt" → "Server Control"
- **Berechtigung**: Nur für Superuser
- **Dokumentation**: Siehe [Health Check API](health_check_api.md) für Details zur externen Überwachung mit Monitoring-Systemen

#### View Application Logs (Log File Viewer)

- **Zweck**: Log-Dateien im Browser anzeigen
- **Features**:
  - Auswahl von Log-Dateien aus dem `logs/` Verzeichnis
  - Echtzeit-Log-Anzeige
  - Rotierte Log-Dateien durchsuchen
  - Filterung und Suche
  - Auto-Refresh-Funktion
- **Zugriff**: `/admin/logs/` oder über "Mgmt" → "View Application Logs"
- **Berechtigung**: Nur für Superuser
- **Dokumentation**: 
  - [Log-Dateien im Admin GUI anzeigen](logging.md) - Übersicht über Log-Dateien und Verwendung des Log File Viewers
  - [Production Logging Setup](logging_production_setup.md) - Best Practices für Logging in der Produktion

#### Backup Management

- **Zweck**: Datenbank-Backups erstellen und verwalten
- **Features**:
  - Manuelle Backup-Erstellung
  - Backup-Liste anzeigen
  - Backup-Download
  - Backup-Informationen (Größe, Datum)
- **Zugriff**: `/admin/backup/` oder über "Mgmt" → "Backup Management"
- **Berechtigung**: Nur für Superuser

#### Gunicorn Configuration

- **Zweck**: Gunicorn-Log-Level und Worker-Konfiguration
- **Wichtige Felder**:
  - `log_level`: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - `worker_class`: Worker-Klasse (`sync` oder `gthread`)
  - `workers`: Anzahl der Worker-Prozesse
  - `threads`: Anzahl der Threads pro Worker (nur bei `gthread`)
- **Features**:
  - Log-Level direkt im Admin GUI ändern
  - Worker-Konfiguration anpassen
  - Keine Environment-Variablen nötig
  - Singleton-Model (nur eine Instanz)
- **Zugriff**: `/admin/mgmt/gunicornconfig/` oder über "Mgmt" → "Gunicorn Configuration"
- **Hinweis**: Nach Änderung ist ein Server-Neustart erforderlich
- **Dokumentation**: 
  - [Gunicorn-Konfiguration im Admin GUI](gunicorn_config.md) - Übersicht über die Konfiguration im Admin Interface
  - [Gunicorn Worker Konfiguration](gunicorn_worker_configuration.md) - Details zu Worker-Klassen, Signal-Handler-Problemen und Performance

#### Application Logs

**Hinweis:** Logs werden nicht mehr in der Datenbank gespeichert. Verwenden Sie stattdessen den **Log File Viewer** (siehe oben), um Log-Dateien anzuzeigen.

**Dokumentation**: Siehe [Log-Dateien im Admin GUI anzeigen](logging.md) und [Production Logging Setup](logging_production_setup.md) für Details zum Logging-System.

#### Request Logs

- **Zweck**: HTTP-Request-Logs für Performance-Analysen
- **Features**:
  - Request-Dauer anzeigen
  - Status-Codes filtern
  - Endpunkt-Analysen
  - Performance-Metriken
- **Zugriff**: `/admin/mgmt/requestlog/` oder über "Mgmt" → "Request Logs"

#### Performance Metrics

- **Zweck**: System-Performance-Metriken überwachen
- **Features**:
  - CPU- und Memory-Statistiken
  - Request-Durchsatz
  - Response-Zeiten
  - Trend-Analysen
- **Zugriff**: `/admin/mgmt/performancemetric/` oder über "Mgmt" → "Performance Metrics"

#### Alert Rules

- **Zweck**: Alert-Regeln für Performance-Überwachung konfigurieren
- **Features**:
  - Schwellenwerte definieren
  - Alert-Bedingungen konfigurieren
  - Benachrichtigungen einrichten
- **Zugriff**: `/admin/mgmt/alertrule/` oder über "Mgmt" → "Alert Rules"

#### Maintenance Control

- **Zweck**: Maintenance Mode aktivieren/deaktivieren und IP-Whitelist konfigurieren
- **Features**:
  - Maintenance Mode aktivieren/deaktivieren
  - IP-Whitelist konfigurieren (einzelne IPs und CIDR-Blöcke)
  - Admin-Zugriff während Wartung erlauben/verbieten
  - Aktuellen Status anzeigen
  - IP-Status prüfen (ob aktuelle IP in Whitelist ist)
- **Zugriff**: `/admin/maintenance/` oder über "Mgmt" → "Maintenance Control"
- **Berechtigung**: Nur für Superuser
- **Dokumentation**: Siehe [Maintenance Mode Setup](apache_maintenance_setup.md) für Details zur Konfiguration, IP-Whitelist und Apache-Integration.

#### Maintenance Configuration

- **Zweck**: IP-Whitelist und Admin-Zugriff konfigurieren
- **Wichtige Felder**:
  - `ip_whitelist`: IP-Adressen oder CIDR-Blöcke (eine pro Zeile)
  - `allow_admin_during_maintenance`: Admin-Zugriff für Superuser erlauben
- **Zugriff**: `/admin/mgmt/maintenanceconfig/` oder über "Mgmt" → "Maintenance Configurations"
- **Berechtigung**: Nur für Superuser
- **Dokumentation**: Siehe [Maintenance Mode Setup](apache_maintenance_setup.md) für Details zur IP-Whitelist-Konfiguration.

#### Minecraft Control

- **Zweck**: Minecraft-Worker-Status und -Steuerung
- **Features**:
  - Worker-Status anzeigen (Minecraft-Bridge-Worker und Snapshot-Worker)
  - Worker starten, stoppen, neustarten
  - Coin-Synchronisation zwischen MyCyclingCity und Minecraft-Server verwalten
  - Outbox-Events anzeigen und verwalten
  - RCON-Verbindung testen
  - Manuelle Synchronisation auslösen
- **Zugriff**: `/admin/minecraft/` oder über "Minecraft Verwaltung" → "Minecraft Control"
- **Berechtigung**: Nur für Superuser
- **Hinweis**: Der Worker synchronisiert Coins zwischen der Django-Datenbank und dem Minecraft-Server über RCON. Er steuert nicht den Minecraft-Server selbst.
- **Dokumentation**: Siehe [Minecraft-Integration](minecraft.md) für Details zur Coin-Synchronisation, RCON-Kommunikation, Outbox-Pattern und Konfiguration.

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

## Häufige Verwaltungsaufgaben

### Server neu starten

1. Navigieren Sie zu **Mgmt** → **Server Control**
2. Prüfen Sie den aktuellen Server-Status
3. Klicken Sie auf **Restart Server**
4. Warten Sie, bis der Neustart abgeschlossen ist

### Log-Dateien anzeigen

1. Navigieren Sie zu **Mgmt** → **View Application Logs**
2. Wählen Sie eine Log-Datei aus dem Dropdown-Menü
3. Die Log-Datei wird automatisch aktualisiert (Auto-Refresh)
4. Verwenden Sie die Suchfunktion, um nach spezifischen Einträgen zu suchen

### Backup erstellen

1. Navigieren Sie zu **Mgmt** → **Backup Management**
2. Klicken Sie auf **Create Backup**
3. Warten Sie, bis das Backup erstellt wurde
4. Laden Sie das Backup herunter, falls nötig

### Gunicorn Log-Level ändern

1. Navigieren Sie zu **Mgmt** → **Gunicorn Configuration**
2. Wählen Sie das gewünschte Log-Level aus
3. Klicken Sie auf **Speichern**
4. **Wichtig**: Starten Sie den Server neu (siehe "Server neu starten")

### Analytics anzeigen

1. Navigieren Sie zu **Historische Berichte & Analysen** → **Analytics Dashboard**
2. Wählen Sie den gewünschten Zeitraum
3. Wählen Sie die zu analysierenden Gruppen
4. Exportieren Sie die Daten bei Bedarf

### Session-Status überwachen

1. Navigieren Sie zu **Session Management** → **Session Dashboard**
2. Sehen Sie alle aktiven Sessions
3. Klicken Sie auf eine Session, um Details anzuzeigen
4. Beenden Sie Sessions bei Bedarf

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
- [Production Deployment Checklist](PRODUCTION_CHECKLIST.md) - Checkliste für Production-Deployments
- [Übersetzungen kompilieren](COMPILE_MESSAGES.md) - Anleitung zum Kompilieren von Übersetzungen ohne venv-Bibliotheken
- [Maintenance Mode Setup](apache_maintenance_setup.md) - Maintenance Mode mit IP-Whitelist und Admin-Zugriff konfigurieren