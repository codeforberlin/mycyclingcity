# Mileage Consistency Fix

## Problem Identified

**Root Cause:** HourlyMetrics contained more data than `Player.distance_total` (the master data source).

### The Issue

1. **Player.distance_total is the MASTER data source** - written directly via `update_data` API endpoint
2. **HourlyMetrics are HISTORY data** - should reflect how `Player.distance_total` was accumulated through sessions
3. **Inconsistency:** HourlyMetrics sum > Player.distance_total for several test players

### Why This Happened

The `load_test_data` command was creating HourlyMetrics directly AND updating `player.distance_total`. If:
- The command was run multiple times
- Or `player.distance_total` was updated via `update_data` AFTER `load_test_data`
- Then the data would become inconsistent

## Solution Implemented

### 1. Fixed `load_test_data.py`

**Before:** Created HourlyMetrics directly, which could lead to inconsistencies.

**After:** 
- Updates `Player.distance_total` first (master data)
- Then creates HourlyMetrics as if sessions were saved (simulating real-world flow)
- Ensures HourlyMetrics always match Player.distance_total

### 2. Created `analyze_mileage_consistency.py`

A new management command that:
- **Analyzes** all players for inconsistencies between `Player.distance_total` and HourlyMetrics
- **Reports** detailed breakdowns of mismatches
- **Fixes** inconsistencies using strategies:
  - `delete_extra_metrics`: Removes excess HourlyMetrics to match Player.distance_total (conservative approach)

### 3. Fixed Existing Data

Ran the fix command to correct existing inconsistencies:
```bash
python manage.py analyze_mileage_consistency --fix --strategy=delete_extra_metrics
```

**Result:** All 5 inconsistencies fixed. HourlyMetrics now match Player.distance_total.

## Verification

After the fix:
- ✅ All players: HourlyMetrics sum = Player.distance_total
- ✅ All groups: HourlyMetrics sum = Group.distance_total (from member aggregation)
- ✅ No inconsistencies found

## Usage

### Check for Inconsistencies
```bash
python manage.py analyze_mileage_consistency
```

### Fix Inconsistencies
```bash
python manage.py analyze_mileage_consistency --fix --strategy=delete_extra_metrics
```

### Check Specific Player
```bash
python manage.py analyze_mileage_consistency --player-id=42
```

## Data Flow (Correct)

1. **update_data API** → Updates `Player.distance_total` (MASTER)
2. **Session ends** → Saves to HourlyMetric (HISTORY)
3. **Reports** → Use HourlyMetrics for historical breakdowns
4. **Leaderboards/GUIs** → Use `Player.distance_total` for current totals

## Important Notes

- **Player.distance_total is ALWAYS the source of truth** for current totals
- **HourlyMetrics are derived data** that should match Player.distance_total
- **Groups aggregate from Players**, not from HourlyMetrics directly
- **Reports use HourlyMetrics** for time-based breakdowns, but totals should match Player.distance_total

## Prevention

To prevent future inconsistencies:
1. Always update `Player.distance_total` first (master data)
2. Then create HourlyMetrics from sessions (derived data)
3. Never create HourlyMetrics directly without updating Player.distance_total
4. Run `analyze_mileage_consistency` periodically to catch issues early

