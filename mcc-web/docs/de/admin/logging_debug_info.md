# INFO und DEBUG Logs im Admin GUI aktivieren

## Übersicht

Standardmäßig werden nur **WARNING**, **ERROR** und **CRITICAL** Logs in der Datenbank gespeichert und im Admin GUI angezeigt. Um auch **INFO** und **DEBUG** Logs zu sehen, müssen Sie die Option `LOG_DB_DEBUG` aktivieren.

## Aktivierung

### Schritt 1: Environment-Variable setzen

Fügen Sie in Ihrer `.env` Datei (im `mcc-web/` Verzeichnis) folgende Zeile hinzu:

```env
LOG_DB_DEBUG=True
```

### Schritt 2: Django-Server neu starten

Nach dem Ändern der `.env` Datei müssen Sie den Django-Server neu starten:

```bash
# Server stoppen (Ctrl+C)
# Dann neu starten:
python manage.py runserver
```

Oder wenn Sie Gunicorn verwenden:

```bash
/path/to/mcc-web/scripts/mcc-web.sh restart
```

Hinweis: In der aktuellen Produktion läuft die Anwendung als Benutzer `mcc`
unter `/data/games/mcc/mcc-web`. Passen Sie Pfade und Benutzer an Ihre Umgebung an.

## Was passiert nach der Aktivierung?

- ✅ **DEBUG** Logs werden in der Datenbank gespeichert
- ✅ **INFO** Logs werden in der Datenbank gespeichert
- ✅ **WARNING** Logs werden weiterhin gespeichert
- ✅ **ERROR** Logs werden weiterhin gespeichert
- ✅ **CRITICAL** Logs werden weiterhin gespeichert

## Wichtige Hinweise

### ⚠️ Datenbank-Größe

Wenn `LOG_DB_DEBUG=True` aktiviert ist, kann die Datenbank schnell wachsen, da sehr viele Log-Einträge gespeichert werden. 

**Empfehlungen:**
- Nur für Debugging/Entwicklung aktivieren
- Regelmäßig alte Logs bereinigen (siehe unten)
- In Produktion nur bei Bedarf aktivieren

### 🧹 Regelmäßige Bereinigung

Verwenden Sie das Cleanup-Command, um alte Logs zu löschen:

```bash
# Alle Logs älter als 7 Tage löschen
python manage.py cleanup_application_logs --days 7

# Nur DEBUG/INFO Logs löschen (älter als 1 Tag)
python manage.py cleanup_application_logs --days 1 --level INFO
```

### 📊 Cron-Job für automatische Bereinigung

Für Produktion empfohlen:

```bash
# Täglich um 3 Uhr morgens DEBUG/INFO Logs älter als 1 Tag löschen
0 3 * * * cd /path/to/mcc-web && python manage.py cleanup_application_logs --days 1 --level INFO

# Wöchentlich alle Logs älter als 30 Tage löschen
0 4 * * 0 cd /path/to/mcc-web && python manage.py cleanup_application_logs --days 30
```

## Testen

Nach der Aktivierung können Sie testen:

```bash
python manage.py test_logging
```

Dieses Command generiert Test-Logs für alle Levels. Nach 5-6 Sekunden sollten Sie im Admin GUI (`/admin/mgmt/applicationlog/`) auch INFO und DEBUG Logs sehen.

## Deaktivierung

Um DEBUG/INFO Logging wieder zu deaktivieren:

1. In `.env` Datei ändern:
```env
LOG_DB_DEBUG=False
```

2. Django-Server neu starten

## Filterung im Admin

Im Admin GUI können Sie nach Log-Level filtern:

1. Gehen Sie zu `/admin/mgmt/applicationlog/`
2. Klicken Sie auf "Level" in der Filter-Sidebar
3. Wählen Sie "DEBUG" oder "INFO" aus

## Performance

- **Batch-Processing**: Logs werden in Batches von 10 Einträgen gespeichert
- **Asynchron**: Das Schreiben erfolgt in einem Hintergrund-Thread
- **Indizes**: Die Datenbank hat Indizes für schnelle Abfragen

Bei sehr hohem Log-Volumen kann es zu einer leichten Verzögerung kommen (max. 5 Sekunden).
