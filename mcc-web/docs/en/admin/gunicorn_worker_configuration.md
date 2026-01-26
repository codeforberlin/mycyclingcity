# Gunicorn Worker Configuration

## Overview

This document explains the differences between different Gunicorn worker classes, when they become relevant, and how to avoid signal handler issues with Minecraft RCON.

## Gunicorn Worker vs. Minecraft Worker

### Gunicorn Worker

**What are Gunicorn Workers?**
- Web server processes that handle HTTP requests
- Process requests from:
  - MCC devices (every 10 seconds)
  - Admin GUI (e.g., Snapshot button)
  - Web browsers (user requests)

**Configuration:**
- Count: Configurable (default: CPU * 2 + 1)
- Worker class: `sync` or `gthread`
- Threads: Only relevant with `gthread`

### Minecraft Worker

**What are Minecraft Workers?**
- Separate background processes (not part of Gunicorn)
- `minecraft_bridge_worker`: Processes outbox events
- `minecraft_snapshot_worker`: Periodically updates snapshots
- Run in main thread → **no signal problems**

**Important:** This documentation refers to **Gunicorn Workers**, not Minecraft Workers.

## Worker Classes: sync vs. gthread

### sync Worker

**How it works:**
- 1 request per worker simultaneously
- Blocking: Worker waits until request is finished
- Simple, but less efficient for I/O

**Advantages:**
- No signal handler problems
- Simple configuration
- Stable

**Disadvantages:**
- Less efficient for I/O-intensive operations
- Requests may wait under high load

### gthread Worker

**How it works:**
- Multiple requests per worker simultaneously (via threads)
- Non-blocking for I/O: While one thread waits, another can work
- More efficient for I/O-intensive operations

**Advantages:**
- Better performance for I/O-intensive operations
- More simultaneous requests possible

**Disadvantages:**
- **Signal handler problems** with `mcrcon` (Minecraft RCON)
- More complex configuration

## Signal Handler Problem

### Problem Description

**Error:**
```
signal only works in main thread of the main interpreter
```

**Cause:**
- `mcrcon` (Minecraft RCON library) uses signal handlers for timeouts
- Signal handlers only work in the main thread
- With `gthread` workers, requests run in threads, not the main thread
- → Signal error when calling snapshot from Admin GUI

**When does it occur?**
- When a Gunicorn worker (in a thread with `gthread`) directly calls `refresh_scoreboard_snapshot()`
- E.g., when clicking "Update Snapshot" in Admin GUI

**When does it NOT occur?**
- Minecraft workers run as separate processes in main thread → no problems
- Normal requests without RCON calls → no problems

### Solution

**Option 1: Change worker class to `sync` (recommended)**
- Advantage: Simple, fixes problem immediately
- Disadvantage: Lower performance for I/O-intensive requests
- Procedure: In Admin GUI (`/admin/mgmt/gunicornconfig/`) change `worker_class` from `gthread` to `sync`

**Option 2: Make RCON client thread-safe**
- Advantage: `gthread` remains, better performance
- Disadvantage: Code change required
- Status: Not yet implemented

## When Does the Difference Matter?

### Low Load (< 1 Request/Second)
- Difference barely noticeable
- Both configurations are sufficient

### Medium Load (1-5 Requests/Second)
- `sync`: May cause wait times if requests overlap
- `gthread`: Can process multiple requests in parallel
- Difference: Noticeable, but usually still acceptable

### High Load (> 5 Requests/Second)
- `sync`: Requests must wait until worker is free
- `gthread`: Can process multiple requests in parallel
- Difference: Clearly noticeable

### Specific to MCC-Web

**I/O-intensive operations:**
- Database access (SQLite)
- RCON connections (Minecraft)
- File operations (logs, media)
- HTTP requests (if present)

**For these operations:**
- `sync`: Worker blocks during I/O
- `gthread`: Other threads can continue working

## Practical Impact

### With 1 Worker

| Scenario | `sync` | `gthread` (2 Threads) |
|----------|--------|------------------------|
| 1 simultaneous request | ✅ OK | ✅ OK |
| 2 simultaneous requests | ⚠️ 1 waits | ✅ Both parallel |
| 3 simultaneous requests | ⚠️ 2 wait | ⚠️ 2 parallel, 1 waits |
| 10 simultaneous requests | ⚠️ 9 wait | ⚠️ 2 parallel, 8 wait |

### Load Calculation for MCC Devices

**Assumption:**
- 30-40 MCC stations active
- One request every 10 seconds per station
- Average: 35 stations

**Calculation:**
- 35 requests / 10 seconds = **3.5 requests/second**
- Maximum simultaneous: Theoretically up to 35 (if all send exactly at the same time)
- Practically: Usually 1-5 simultaneous (due to time offset)

**With 2-3 workers (`sync`):**
- 2 workers: 2 simultaneous requests → **sufficient**
- 3 workers: 3 simultaneous requests → **more than sufficient**

## RAM Usage

### Typical RAM Usage

**With `sync` worker (no threads):**
- Base: ~50-80 MB (Python + Django)
- Django app code: ~20-30 MB
- Database connections: ~5-10 MB
- Request buffer: ~5-10 MB
- **Total: ~80-130 MB per worker**

**With `gthread` worker (2 threads):**
- Base: ~80-130 MB
- Additional per thread: ~10-20 MB
- **Total: ~100-150 MB per worker**

### Memory Calculation for MCC-Web

**Option 1: 2 workers with `sync`**
- 2 × ~100 MB = ~200 MB
- Plus master: ~150 MB
- **Total: ~350 MB**

**Option 2: 3 workers with `sync`**
- 3 × ~100 MB = ~300 MB
- Plus master: ~150 MB
- **Total: ~450 MB**

**Additionally:**
- Minecraft workers: ~100-200 MB (2 processes)
- **Total system: ~450-650 MB**

### Comparison

| Configuration | RAM Usage | Capacity |
|---------------|-----------|----------|
| 1 worker (`gthread`, 2 threads) | ~300 MB | 2 simultaneous |
| 2 workers (`sync`) | ~350 MB | 2 simultaneous |
| 3 workers (`sync`) | ~450 MB | 3 simultaneous |

## Recommendations

### For 30-40 MCC Stations

**Recommended configuration:**
- **Worker class:** `sync` (avoids signal problems)
- **Worker count:** 2-3 (sufficient for 3.5 requests/second)
- **RAM usage:** ~350-450 MB (manageable)

**Rationale:**
- 2-3 workers with `sync` = 2-3 simultaneous requests
- Average: 3.5 requests/second → sufficient
- Peak load: Usually 1-5 simultaneous → 2-3 workers sufficient
- Signal problems are fixed

### When Should You Use `gthread`?

**Recommended for:**
- > 2 simultaneous requests
- I/O-intensive operations (DB, network, files)
- Multiple workers (3+)
- **AND:** RCON client must be thread-safe (Option 2 implemented)

**Not needed for:**
- Low load (< 1 request/second)
- Few workers (1-2)
- CPU-intensive operations (threads don't help here)

## Changing Configuration

### In Admin GUI

1. Go to `/admin/mgmt/gunicornconfig/`
2. Change `worker_class` from `gthread` to `sync`
3. Set `workers` to 2 or 3
4. Save
5. Restart server: `/data/appl/mcc/mcc-web/scripts/mcc-web.sh restart`

### With Management Command

```bash
cd /data/appl/mcc/mcc-web
source /data/appl/mcc/venv/bin/activate
python manage.py set_gunicorn_sync
```

Then restart server:
```bash
/data/appl/mcc/mcc-web/scripts/mcc-web.sh restart
```

## Summary

- **Gunicorn Workers** process HTTP requests (not to be confused with Minecraft Workers)
- **`sync`** workers avoid signal handler problems with `mcrcon`
- **2-3 workers** with `sync` are sufficient for 30-40 MCC stations
- **RAM usage** is manageable (~350-450 MB)
- Changing to `sync` is a good solution for the current situation
