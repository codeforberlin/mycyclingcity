# Mileage Consistency Fix

## Problem Identified

**Root Cause:** HourlyMetrics contained more data than `Cyclist.distance_total` (the master data source).

### The Issue

1. **Cyclist.distance_total is the MASTER data source** - written directly via `update_data` API endpoint
2. **HourlyMetrics are HISTORY data** - should reflect how `Cyclist.distance_total` was accumulated through sessions
3. **Inconsistency:** HourlyMetrics sum > Cyclist.distance_total for several test cyclists

### Why This Happened

The `load_test_data` command was creating HourlyMetrics directly AND updating `cyclist.distance_total`. If:
- The command was run multiple times
- Or `cyclist.distance_total` was updated via `update_data` AFTER `load_test_data`
- Then the data would become inconsistent

## Solution Implemented

### 1. Fixed `load_test_data.py`

**Before:** Created HourlyMetrics directly, which could lead to inconsistencies.

**After:** 
- Updates `Cyclist.distance_total` first (master data)
- Then creates HourlyMetrics as if sessions were saved (simulating real-world flow)
- Ensures HourlyMetrics always match Cyclist.distance_total

### 2. Created `analyze_mileage_consistency.py`

A new management command that:
- **Analyzes** all cyclists for inconsistencies between `Cyclist.distance_total` and HourlyMetrics
- **Reports** detailed breakdowns of mismatches
- **Fixes** inconsistencies using strategies:
  - `delete_extra_metrics`: Removes excess HourlyMetrics to match Cyclist.distance_total (conservative approach)

### 3. Fixed Existing Data

Ran the fix command to correct existing inconsistencies:
```bash
python manage.py analyze_mileage_consistency --fix --strategy=delete_extra_metrics
```

**Result:** All 5 inconsistencies fixed. HourlyMetrics now match Cyclist.distance_total.

## Verification

After the fix:
- ✅ All cyclists: HourlyMetrics sum = Cyclist.distance_total
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

### Check Specific Cyclist
```bash
python manage.py analyze_mileage_consistency --cyclist-id=42
```

## Data Flow (Correct)

1. **update_data API** → Updates `Cyclist.distance_total` (MASTER)
2. **Session ends** → Saves to HourlyMetric (HISTORY)
3. **Reports** → Use HourlyMetrics for historical breakdowns
4. **Leaderboards/GUIs** → Use `Cyclist.distance_total` for current totals

## Important Notes

- **Cyclist.distance_total is ALWAYS the source of truth** for current totals
- **HourlyMetrics are derived data** that should match Cyclist.distance_total
- **Groups aggregate from Cyclists**, not from HourlyMetrics directly
- **Reports use HourlyMetrics** for time-based breakdowns, but totals should match Cyclist.distance_total

## Prevention

To prevent future inconsistencies:
1. Always update `Cyclist.distance_total` first (master data)
2. Then create HourlyMetrics from sessions (derived data)
3. Never create HourlyMetrics directly without updating Cyclist.distance_total
4. Run `analyze_mileage_consistency` periodically to catch issues early

