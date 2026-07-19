#!/bin/bash
#
# Setzt Leserechte (ACL) für mccweb auf die Minecraft-Welt.
# Nur als root oder mcc ausführen – niemals von mccweb-Prozessen.
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

WORLD_DIR="${1:-/data/games/mcc/mc-srv/MyCyclingCity}"
READER_USER="${2:-mccweb}"

if [[ "$(id -u)" -ne 0 ]] && [[ "$(id -un)" != "mcc" ]]; then
    echo "Fehler: Bitte als root oder mcc ausführen (nicht als mccweb)." >&2
    exit 1
fi

if [[ ! -d "${WORLD_DIR}" ]]; then
    echo "Fehler: Welt-Verzeichnis fehlt: ${WORLD_DIR}" >&2
    exit 1
fi

# Parents nur traversieren (kein Listing von /data/games)
for parent in /data/games /data/games/mcc /data/games/mcc/mc-srv; do
    if [[ -d "${parent}" ]]; then
        setfacl -m "u:${READER_USER}:--x" "${parent}"
        echo "Traverse: ${parent} -> u:${READER_USER}:--x"
    fi
done

# Bestehende Dateien/Dirs: lesen; Dirs: default-ACL für neu erzeugte Dateien (nach save-all flush)
find "${WORLD_DIR}" -type d -print0 | while IFS= read -r -d '' dir; do
    setfacl -m "u:${READER_USER}:rX" "${dir}"
    setfacl -d -m "u:${READER_USER}:rX" "${dir}"
done

find "${WORLD_DIR}" -type f -print0 | while IFS= read -r -d '' file; do
    setfacl -m "u:${READER_USER}:r--" "${file}"
done

echo ""
echo "Fertig. Prüfung:"
getfacl "${WORLD_DIR}" | head -n 20
echo "---"
if [[ -f "${WORLD_DIR}/level.dat" ]]; then
    getfacl "${WORLD_DIR}/level.dat"
fi
echo ""
echo "Hinweis: Nach 'save-all flush' erneut prüfen:"
echo "  getfacl ${WORLD_DIR}/level.dat | grep ${READER_USER}"
echo "Wenn der Eintrag fehlt, greift die Default-ACL nicht (z.B. Datei per Rename aus anderem Dir)."
echo "Dann Backup-Cron als User mcc laufen lassen (kein sudo mccweb→mcc)."
