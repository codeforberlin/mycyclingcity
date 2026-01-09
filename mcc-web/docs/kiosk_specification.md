# Specification: Kiosk Leaderboard Dashboard (Live-Sync)

## 1. Layout & Architecture
- **Structure:** Use a single-page `h-screen overflow-hidden` layout using Tailwind CSS.
- **Layers:**
    - **Top (5vh):** Integration of the existing Player Ticker (Live-Active Players).
    - **Header (15vh):** School Banner showing the Top 3 Schools (aggregated mileage).
    - **Main (75vh):** Flexible Auto-Grid for Group Tiles.
    - **Footer (5vh):** Global statistics (Total KM) and Live Activity Counter.
- **Floating Element:** A 'Daily Record' Trophy Badge in the top-right corner, tilted 12 degrees.

## 2. Grid Logic (Group Tiles)
- **Flexibility:** Use `grid-cols-[repeat(auto-fit,minmax(220px,1fr))]`.
- **States (Focus-Dimming):**
    - **Active (<30s):** Green ring, pulse animation, `scale-105`, `z-20`, `opacity-100`.
    - **Idle (<10m):** Standard appearance, `opacity-100`.
    - **Dormant (>10m):** `opacity-40`, `grayscale`, `scale-95`. Use `transition-all duration-1000`.
- **Ranking:** - Rank 1: Gold gradient + Crown Icon + Shadow Glow.
    - Rank 2/3: Silver/Bronze gradients.
    - Others: Dark Slate cards with high-contrast text.

## 3. Data & Sync (Django + HTMX)
- **Optimization:** Use a single view-level calculation for `active_group_ids` and `recent_group_ids` to avoid N+1 queries.
- **Live Counter:** Display a pulsing red dot next to the text "[X] Groups currently pedaling".
- **Daily Record:** Calculate the highest mileage achieved *since 00:00 today* and display the holder's name and value.
- **Updates:** Trigger a full HTMX swap for the Leaderboard section every 20 seconds using `hx-trigger="every 20s"`.
- **Page Rotation:** - Implement a 60-second rotation between the 'Map View' and the 'Leaderboard View'.
    - Use HTMX or a simple `setTimeout` Javascript logic to toggle a `hidden` class or swap the content.
    - Add a visual 'Next swap in X seconds' progress bar at the very bottom to inform viewers.
    - Ensure the OSM map is not re-initialized every time to save performance; hide/show is preferred over re-loading.

## 4. Map Integration (OSM)
- **Context:** The dashboard must coexist with the existing OSM map showing travel tracks and milestones.
- **Toggle/Overlay:** Propose a way to either:
    - Side-by-side: 50% Map / 50% Leaderboard.
    - Overlay: The Leaderboard as a semi-transparent sidebar on the left/right of the map.
- **Requirement:** Ensure the Leaderboard logic (Active Glow) can trigger interactions on the map (e.g., center map on an active group's last milestone).

## 5. Coding Standards (Strict)
- **Language:** All code, comments, and docstrings must be in English.
- **Type Hints:** Use full Python type hinting for all new methods and views.
- **Naming:** Follow Django best practices; use `gettext_lazy` for any German UI strings.

## 6. View Rotation & Manual Override
- **Auto-Rotation:** Toggle between `#map-view` and `#leaderboard-view` every 60 seconds.
- **Progress Indicator:** Display a 2px high progress bar at the bottom (`bg-blue-600`) that resets every 60s.
- **Manual Control:**
    - **Spacebar / Right Arrow:** Immediately skip to the next view and reset the 60s timer.
    - **'P' Key:** Pause/Resume the auto-rotation (show a small 'Paused' icon in a corner).
- **Persistence:** Ensure the OSM map is only initialized once and hidden using CSS `display: none` to preserve zoom levels and markers.

## 7. Group Tile Content & Hierarchy
- **Primary Label:** Display `group.get_kiosk_label` (the short name like '1a') in a very large, bold font.
- **Subtitle:** Display `group.school_name` directly below the primary label in a smaller, semi-transparent font (e.g., `text-sm opacity-70`).
- **Mileage:** The total kilometers (`distance_total`) should be the most prominent numerical element on the tile.
- **Layout:** Use a vertical stack inside the tile: School Name (top) -> Short Name (center) -> KM (bottom).

