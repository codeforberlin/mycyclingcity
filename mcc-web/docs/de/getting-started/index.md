# Erste Schritte

Willkommen zur MyCyclingCity Projekt-Dokumentation.

## Projekt-Übersicht

MyCyclingCity ist eine Django-basierte Web-Anwendung zur Verfolgung von Radaktivitäten, Verwaltung von Gruppen und Anzeige von Bestenlisten.

## Architektur

Das Projekt ist in mehrere Django-Apps organisiert:

- **api**: Kern-API und Modelle für Radler, Gruppen, Events und Kilometer-Tracking
- **map**: OSM/Leaflet Karten-Visualisierung
- **ranking**: Ranglisten-Tabellen und statistische Listen
- **leaderboard**: Animierte High-Score Tiles und Leaderboard-Anzeigen
- **kiosk**: Kiosk-Geräteverwaltung
- **iot**: IoT-Geräteverwaltung
- **game**: Kilometer-Challenge Spiel
- **mgmt**: Verwaltung und Analytics

## Schnelllinks

- [Installations-Anleitung](installation.md) - Entwicklungsumgebung einrichten
- [Konfiguration](configuration.md) - Anwendung konfigurieren
- [API Referenz](../api/index.md) - Vollständige API-Dokumentation
- [Admin GUI Handbuch](../admin/index.md) - Django Admin Interface Anleitung

## Mitwirken

Alle Code-Kommentare und Dokumentation müssen auf Englisch sein.

## Version

Aktuelle Version: Das Projekt verwendet einen Versionserkennungsmechanismus, der:
- Zuerst eine `version.txt` Datei im Projekt-Root prüft
- Auf `git describe --tags --always --dirty` zurückfällt, wenn die Datei nicht existiert
- Die Version ist über Django Settings zugänglich: `settings.get_project_version()`
