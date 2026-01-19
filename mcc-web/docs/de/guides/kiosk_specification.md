# Spezifikation: Kiosk Leaderboard Dashboard (Live-Sync)

## 1. Layout & Architektur
- **Struktur:** Verwenden Sie ein Single-Page `h-screen overflow-hidden` Layout mit Tailwind CSS.
- **Ebenen:**
    - **Oben (5vh):** Integration des bestehenden Cyclist Tickers (Live-Aktive Radler).
    - **Header (15vh):** Schul-Banner mit den Top 3 Schulen (aggregierte Kilometer).
    - **Hauptbereich (75vh):** Flexibles Auto-Grid für Gruppen-Tiles.
    - **Footer (5vh):** Globale Statistiken (Gesamt KM) und Live-Aktivitäts-Zähler.
- **Schwebendes Element:** Ein 'Tagesrekord' Trophäen-Badge in der oberen rechten Ecke, um 12 Grad geneigt.

## 2. Grid-Logik (Gruppen-Tiles)
- **Flexibilität:** Verwenden Sie `grid-cols-[repeat(auto-fit,minmax(220px,1fr))]`.
- **Zustände (Focus-Dimming):**
    - **Aktiv (<30s):** Grüner Ring, Puls-Animation, `scale-105`, `z-20`, `opacity-100`.
    - **Inaktiv (<10m):** Standard-Erscheinungsbild, `opacity-100`.
    - **Ruhend (>10m):** `opacity-40`, `grayscale`, `scale-95`. Verwenden Sie `transition-all duration-1000`.
- **Rangfolge:** - Rang 1: Gold-Gradient + Kronen-Icon + Schatten-Glow.
    - Rang 2/3: Silber/Bronze-Gradienten.
    - Andere: Dunkle Slate-Karten mit hohem Kontrast-Text.

## 3. Daten & Synchronisation (Django + HTMX)
- **Optimierung:** Verwenden Sie eine einzige View-Level-Berechnung für `active_group_ids` und `recent_group_ids`, um N+1-Abfragen zu vermeiden.
- **Live-Zähler:** Zeigen Sie einen pulsierenden roten Punkt neben dem Text "[X] Gruppen fahren gerade".
- **Tagesrekord:** Berechnen Sie die höchste seit 00:00 heute erreichte Kilometerleistung und zeigen Sie den Namen und Wert des Inhabers an.
- **Updates:** Lösen Sie einen vollständigen HTMX-Swap für den Leaderboard-Bereich alle 20 Sekunden mit `hx-trigger="every 20s"` aus.
- **Seiten-Rotation:** - Implementieren Sie eine 60-Sekunden-Rotation zwischen der 'Karten-Ansicht' und der 'Leaderboard-Ansicht'.
    - Verwenden Sie HTMX oder eine einfache `setTimeout` JavaScript-Logik, um eine `hidden`-Klasse umzuschalten oder den Inhalt zu tauschen.
    - Fügen Sie eine visuelle 'Nächster Wechsel in X Sekunden' Fortschrittsleiste ganz unten hinzu, um Zuschauer zu informieren.
    - Stellen Sie sicher, dass die OSM-Karte nicht jedes Mal neu initialisiert wird, um Performance zu sparen; Ausblenden/Einblenden wird gegenüber Neu-Laden bevorzugt.

## 4. Karten-Integration (OSM)
- **Kontext:** Das Dashboard muss mit der bestehenden OSM-Karte koexistieren, die Reise-Tracks und Meilensteine zeigt.
- **Umschalten/Overlay:** Schlagen Sie eine Möglichkeit vor, entweder:
    - Seite-an-Seite: 50% Karte / 50% Leaderboard.
    - Overlay: Das Leaderboard als halbtransparente Seitenleiste links/rechts der Karte.
- **Anforderung:** Stellen Sie sicher, dass die Leaderboard-Logik (Aktiver Glow) Interaktionen auf der Karte auslösen kann (z.B. Karte auf den letzten Meilenstein einer aktiven Gruppe zentrieren).

## 5. Coding-Standards (Strikt)
- **Sprache:** Alle Code-Kommentare und Docstrings müssen auf Englisch sein.
- **Type Hints:** Verwenden Sie vollständige Python-Type-Hints für alle neuen Methoden und Views.
- **Namensgebung:** Folgen Sie Django Best Practices; verwenden Sie `gettext_lazy` für alle deutschen UI-Strings.

## 6. Ansichts-Rotation & Manuelle Überschreibung
- **Auto-Rotation:** Umschalten zwischen `#map-view` und `#leaderboard-view` alle 60 Sekunden.
- **Fortschritts-Indikator:** Zeigen Sie eine 2px hohe Fortschrittsleiste unten (`bg-blue-600`) an, die alle 60s zurückgesetzt wird.
- **Manuelle Steuerung:**
    - **Leertaste / Rechts-Pfeil:** Sofort zur nächsten Ansicht springen und den 60s-Timer zurücksetzen.
    - **'P'-Taste:** Auto-Rotation pausieren/fortsetzen (zeigen Sie ein kleines 'Pausiert'-Icon in einer Ecke).
- **Persistenz:** Stellen Sie sicher, dass die OSM-Karte nur einmal initialisiert wird und mit CSS `display: none` ausgeblendet wird, um Zoom-Level und Marker zu erhalten.

## 7. Gruppen-Tile-Inhalt & Hierarchie
- **Primäres Label:** Zeigen Sie `group.get_kiosk_label` (den kurzen Namen wie '1a') in einer sehr großen, fetten Schrift an.
- **Untertitel:** Zeigen Sie `group.school_name` direkt unter dem primären Label in einer kleineren, halbtransparenten Schrift an (z.B. `text-sm opacity-70`).
- **Kilometerleistung:** Die Gesamtkilometer (`distance_total`) sollten das prominenteste numerische Element auf dem Tile sein.
- **Layout:** Verwenden Sie einen vertikalen Stack innerhalb des Tiles: Schulname (oben) -> Kurzname (Mitte) -> KM (unten).
