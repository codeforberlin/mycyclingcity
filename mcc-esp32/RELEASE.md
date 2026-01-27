# Release System Dokumentation

Dieses Dokument beschreibt das automatisierte Build- und Release-System für die mcc-esp32 Firmware.

## Übersicht

Das Release-System erstellt automatisch Firmware-Binärdateien für alle unterstützten Hardware-Environments und stellt diese als GitHub Releases bereit.

## Versionierung

Die Version wird in folgender Priorität bestimmt:

1. **Git Tag** (z.B. `v1.0.0` → Version `1.0.0`)
2. **VERSION-Datei** (falls kein Tag vorhanden)
3. **Default**: `1.0.0`

### Version setzen

**Für ein Release:**
```bash
# Erstelle einen Git Tag
git tag v1.0.0
git push origin v1.0.0
```

**Für lokale Builds:**
```bash
# Setze Environment-Variable
export FIRMWARE_VERSION=1.0.0
pio run -e heltec_wifi_lora_32_V3

# Oder bearbeite die VERSION-Datei
echo "1.0.0" > mcc-esp32/VERSION
```

## Automatische Releases

### Release bei Git Tag

Wenn ein Git Tag mit dem Format `v*.*.*` (z.B. `v1.0.0`) gepusht wird:

1. GitHub Actions Workflow wird automatisch getriggert
2. Alle Environments werden gebaut:
   - `heltec_wifi_lora_32_V3`
   - `heltec_wifi_lora_32_V2`
   - `wemos_d1_mini32`
3. Binärdateien werden umbenannt:
   - `mcc-esp32-heltec_wifi_lora_32_V3-1.0.0.bin`
   - `mcc-esp32-heltec_wifi_lora_32_V2-1.0.0.bin`
   - `mcc-esp32-wemos_d1_mini32-1.0.0.bin`
4. Checksummen werden generiert (MD5 und SHA256)
5. GitHub Release wird erstellt mit:
   - Automatisch generierten Release Notes
   - Allen Binärdateien als Assets
   - Checksum-Dateien

### Nightly Builds

Bei Push auf den `main` Branch:

1. Workflow wird getriggert
2. Builds werden erstellt (gleicher Prozess wie Release)
3. Artefakte werden als GitHub Actions Artifacts hochgeladen (30 Tage Retention)
4. **Kein GitHub Release** wird erstellt (nur für Tags)

### Manueller Trigger

Der Workflow kann manuell über die GitHub Actions UI getriggert werden:

1. Gehe zu **Actions** → **Build and Release ESP32 Firmware**
2. Klicke auf **Run workflow**
3. Optional: Version angeben (sonst wird aus Tag/VERSION-Datei extrahiert)

## Dateinamen-Konvention

Alle Binärdateien folgen diesem Format:

```
mcc-esp32-<environment>-<version>.bin
```

**Beispiele:**
- `mcc-esp32-heltec_wifi_lora_32_V3-1.0.0.bin`
- `mcc-esp32-heltec_wifi_lora_32_V2-1.0.0.bin`
- `mcc-esp32-wemos_d1_mini32-1.0.0.bin`

## Checksummen

Für jede Binärdatei werden zwei Checksum-Dateien erstellt:

- `*.bin.md5` - MD5 Hash
- `*.bin.sha256` - SHA256 Hash

**Verifikation:**
```bash
# MD5
md5sum -c mcc-esp32-heltec_wifi_lora_32_V3-1.0.0.bin.md5

# SHA256
sha256sum -c mcc-esp32-heltec_wifi_lora_32_V3-1.0.0.bin.sha256
```

## Release Notes

Release Notes werden automatisch generiert und enthalten:

- Liste aller Binärdateien mit Größe und Checksummen
- Commits seit dem letzten Tag (für Tag-Releases)
- Build-Informationen (Datum, Commit-Hash)

## Lokale Builds

Für lokale Builds mit Version:

```bash
cd mcc-esp32

# Version setzen
export FIRMWARE_VERSION=1.0.0

# Build für ein Environment
pio run -e heltec_wifi_lora_32_V3

# Build für alle Environments
pio run
```

Die Binärdateien finden sich in:
```
.pio/build/<environment>/firmware.bin
```

## Workflow-Dateien

- **`.github/workflows/mcc-esp32-build-release.yml`** - Haupt-Workflow für Builds und Releases
- **`mcc-esp32/scripts/extract_version.py`** - Version-Extraktion (Git Tag > VERSION-Datei > Default)
- **`mcc-esp32/scripts/pre_build_version.py`** - Pre-Build-Script für PlatformIO
- **`mcc-esp32/VERSION`** - Fallback-Version-Datei

## Troubleshooting

### Version wird nicht korrekt gesetzt

- Prüfe, ob `FIRMWARE_VERSION` Environment-Variable gesetzt ist
- Prüfe, ob `VERSION`-Datei existiert und korrekt formatiert ist
- Prüfe Git Tags: `git tag -l`

### Build schlägt fehl

- Prüfe PlatformIO Installation
- Prüfe, ob alle Dependencies installiert sind
- Prüfe Workflow-Logs in GitHub Actions

### Release wird nicht erstellt

- Prüfe, ob Git Tag korrekt gepusht wurde
- Prüfe, ob Workflow erfolgreich durchgelaufen ist
- Prüfe GitHub Permissions (GITHUB_TOKEN)

## Weitere Informationen

- [PlatformIO Documentation](https://docs.platformio.org/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Semantic Versioning](https://semver.org/)
