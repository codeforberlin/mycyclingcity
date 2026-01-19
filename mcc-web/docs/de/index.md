# MyCyclingCity Dokumentation

Willkommen zur MyCyclingCity Projekt-Dokumentation.

## Schnellstart

- [Erste Schritte](getting-started/index.md) - Installations- und Setup-Anleitung
- [Admin GUI Handbuch](admin/index.md) - Django Admin Interface Anleitung
- [API Referenz](api/index.md) - Vollständige API-Dokumentation

## Dokumentations-Bereiche

### Erste Schritte

Lernen Sie, wie Sie MyCyclingCity einrichten und konfigurieren:

- [Installations-Anleitung](getting-started/installation.md) - Entwicklungsumgebung einrichten
- [Konfigurations-Anleitung](getting-started/configuration.md) - Anwendung konfigurieren

### Admin GUI Handbuch

Umfassende Anleitung zum Django Admin Interface:

- [Admin GUI Handbuch](admin/index.md) - Radler, Gruppen, Geräte und mehr verwalten

### API Referenz

Vollständige API-Dokumentation:

- [API Referenz](api/index.md) - Alle API-Endpunkte und Modelle

### Anleitungen

Detaillierte Anleitungen für spezifische Features:

- [Live-Karte](guides/map.md) - Interaktive Karte mit Echtzeit-Tracking
- [Spiel (Kilometer-Challenge)](guides/game.md) - Spiel-Räume und Challenge-System
- [Kiosk Spezifikation](guides/kiosk_specification.md) - Kiosk Dashboard Spezifikation

## Projekt-Übersicht

MyCyclingCity ist eine Django-basierte Web-Anwendung zur Verfolgung von Radaktivitäten, Verwaltung von Gruppen und Anzeige von Bestenlisten.

### Architektur

Das Projekt ist in mehrere Django-Apps organisiert:

- **api**: Kern-API und Modelle für Radler, Gruppen, Events und Kilometer-Tracking
- **map**: OSM/Leaflet Karten-Visualisierung
- **ranking**: Ranglisten-Tabellen und statistische Listen
- **leaderboard**: Animierte High-Score Tiles und Leaderboard-Anzeigen
- **kiosk**: Kiosk-Geräteverwaltung
- **iot**: IoT-Geräteverwaltung
- **game**: Kilometer-Challenge Spiel
- **mgmt**: Verwaltung und Analytics

## Mitwirken

Alle Code-Kommentare und Dokumentation müssen auf Englisch sein.

## Version

Aktuelle Version: Das Projekt verwendet einen Versionserkennungsmechanismus, der:
- Zuerst eine `version.txt` Datei im Projekt-Root prüft
- Auf `git describe --tags --always --dirty` zurückfällt, wenn die Datei nicht existiert
- Die Version ist über Django Settings zugänglich: `settings.get_project_version()`
