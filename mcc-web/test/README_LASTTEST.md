# Lasttest Phase A/B – Integration PROD

Ziel: Last auf Gunicorn (`127.0.0.1:8001`) + Minecraft-Worker (Outbox/SQLite), inkl. optionaler Shop-Spends.

## Geräte / Radler (fest)

| Gerät | id_tag | Radler | Radumfang |
|---|---|---|---|
| mcc-test-001 | ketteD | KetteD | 1596 mm (20″) |
| mcc-test-002 | dynamoD | DynamoD | 1596 mm (20″) |
| mcc-test-003 | speicheD | SpeicheD | 1916 mm (24″) |
| mcc-test-004 | kurbelD | KurbelD | 1916 mm (24″) |

JSON: `lasttest_4raeder.json`

## Vorbereitung

```bash
# 1) Geräte anlegen / Wheel-Sizes setzen, Radler prüfen
cd /data/appl/mcc/mcc-web
/data/appl/mcc/venv/bin/python3 /nas/public/dev/mycyclingcity/mcc-web/test/prepare_lasttest_devices.py

# 2) Worker + Web laufen lassen
/data/appl/mcc/mcc-web/scripts/minecraft.sh status
/data/appl/mcc/mcc-web/scripts/mcc-web.sh status

# 3) Optional: Outbox-Stand notieren (Admin oder shell)
```

`mcc_api_test.cfg` muss `server_port = 8001` haben. API-Key kommt aus `MCC_APP_API_KEY` (Django-Settings), nicht aus dem Placeholder in der cfg.

## Phase A – 4 Räder / 5 s (Near-live)

Standard-Sendeintervall für Tests: **5 s** (ESP32-Empfehlung für Scoreboard-Feeling).

```bash
cd /nas/public/dev/mycyclingcity/mcc-web/test
./run_lasttest_phase_a.sh --dry-run   # nur anzeigen
./run_lasttest_phase_a.sh            # starten (4 Prozesse, Default 5s)
LASTTEST_INTERVAL=10 ./run_lasttest_phase_a.sh   # optional anderes Intervall
tail -f .lasttest_phase_a/logs/mcc-test-001.log
./stop_lasttest_phase_a.sh           # stoppen
```

Jeder Prozess: `mcc_api_test.py --loop --interval 5 --device … --id_tag … --wheel-size …`

## Phase B – Shop-Spend (Outbox-Last)

```bash
cd /data/appl/mcc/mcc-web
/data/appl/mcc/venv/bin/python3 /nas/public/dev/mycyclingcity/mcc-web/test/shop_spend_load_test.py --list

# Django-Pfad (gleicher Outbox-Effekt wie WS-Spend):
/data/appl/mcc/venv/bin/python3 /nas/public/dev/mycyclingcity/mcc-web/test/shop_spend_load_test.py \
  --interval 15 --amount 1 --amount-max 5 --duration 600
```

Optional WS-Pfad (`--mode ws`), wenn Daphne/WS aktiv und `websockets` im venv installiert ist.

## Erfolgskriterien (Phase C)

- Worker-PID bleibt stabil
- Kein fataler Exit mit `database is locked`
- Outbox pending wird abgearbeitet (schwankt ok)
- Phase-A Logs zeigen überwiegend erfolgreiche Sends
