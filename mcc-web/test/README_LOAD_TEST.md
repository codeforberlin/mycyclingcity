# Leaderboard Load Test Script

## Overview

The `load_test_leaderboards.py` script performs load tests for leaderboard endpoints by:
1. Loading all devices and cyclists from the database
2. Sending HTTP requests to `update-data` endpoints to simulate activity
3. **Live leaderboard display during execution** - shows active cyclists and top rankings after each iteration
4. Testing leaderboard endpoints (Cyclists, Groups)
5. Verifying data in leaderboards
6. Generating a test report

## Prerequisites

- Django server must be running (either `python manage.py runserver` or Gunicorn)
- Database must contain devices and cyclists
- API keys must be configured for devices (automatically generated for test devices)

## Usage

### Basic Usage

```bash
# Standard test (10 iterations, 1 second delay)
python test/load_test_leaderboards.py

# With custom parameters
python test/load_test_leaderboards.py --iterations 20 --delay 0.5

# With different server
python test/load_test_leaderboards.py --base-url http://localhost:8001

# With custom output file
python test/load_test_leaderboards.py --output my_test_results.json
```

### Parameters

- `--base-url`: Base URL of the API server (default: from `mcc_api_test.cfg` or `http://localhost:8000`)
- `--iterations`: Number of test iterations (default: 10)
- `--delay`: Delay between iterations in seconds (default: 1.0)
- `--output`: Output filename for results (default: `load_test_results.json`)
- `--no-live-leaderboard`: Disables live leaderboard display during execution

## What the Script Does

1. **Loads data from database:**
   - All visible devices with kilometer collection enabled
   - All visible cyclists with kilometer collection enabled

2. **Sends update requests:**
   - Simulates random combinations of devices and cyclists
   - Sends `distance_delta` values between 0.1 and 5.0 km
   - Uses device API keys (or global API key)

3. **Shows live leaderboard during execution:**
   - Active cyclists (with session kilometers and device)
   - Top 5 cyclists (Total)
   - Top 5 cyclists (Today)
   - Top 5 groups (Total)
   - Updated after each iteration

4. **Tests leaderboard endpoints:**
   - `get-leaderboard/cyclists` (total and daily)
   - `get-leaderboard/groups` (total and daily)
   - `get-cyclist-distance/{identifier}`
   - `get-group-distance/{identifier}`

5. **Generates report:**
   - Saves all results in JSON format (including live leaderboard snapshots)
   - Shows summary in console

## Output

The script creates a JSON file with the following information:

```json
{
  "start_time": "2025-12-31T12:00:00",
  "end_time": "2025-12-31T12:05:00",
  "duration_seconds": 300.0,
  "base_url": "http://localhost:8000",
  "iterations": 10,
  "devices_tested": 26,
  "players_tested": 14,
  "updates_sent": 50,
  "updates_successful": 48,
  "updates_failed": 2,
  "leaderboard_tests": [
    {
      "test": "players_total",
      "sort": "total",
      "success": true,
      "entries_count": 10,
      "data": {...}
    }
  ],
  "errors": []
}
```

## Example Execution

```bash
$ python test/load_test_leaderboards.py --iterations 5

================================================================================
Leaderboard Load Test
================================================================================
Base URL: http://127.0.0.1:8000
Iterations: 5
Delay between iterations: 1.0s

Loading devices and cyclists from database...
Found 26 devices and 14 players

Using API key: MCC-APP-API-KEY-SE...

Starting load test iterations...
--------------------------------------------------------------------------------

Iteration 1/5
  ✓ Update: device-01 -> cyclist-01 (+2.34 km)
  ✓ Update: device-02 -> cyclist-02 (+1.56 km)
  ...

================================================================================
📊 Live Leaderboard - Iteration 1
================================================================================

🟢 Active Cyclists (5):
   1. cyclist-01        | Session:   2.34 km | Total:    15.80 km | Device: device-01
   2. cyclist-02        | Session:   1.56 km | Total:     8.70 km | Device: device-02
   ...

🏆 Top 5 Players (Total):
  1. cyclist-01         -    15.80 km
  2. cyclist-02         -     8.70 km
   ...

📅 Top 5 Cyclists (Today):
  1. cyclist-01         -     2.34 km
  2. cyclist-02         -     1.56 km
   ...

🏫 Top 5 Groups (Total):
  1. SchuleA                    -    24.50 km
  2. Klasse 1a                  -    15.80 km
   ...
================================================================================

Testing leaderboard endpoints...
--------------------------------------------------------------------------------

Testing players_total (sort=total)...
  ✓ Success: 10 entries returned

Testing players_daily (sort=daily)...
  ✓ Success: 10 entries returned

...

Results saved to: test/load_test_results.json

================================================================================
Test Summary
================================================================================
Duration: 15.23 seconds
Devices tested: 26
Players tested: 14
Updates sent: 25
Updates successful: 25
Updates failed: 0
Leaderboard tests: 4
Successful leaderboard tests: 4/4

✓ No errors!
================================================================================
```

## Reusability

The script is designed to be reusable:

1. **Automatic API key detection:**
   - Uses device-specific API keys if available
   - Falls back to global API key from `mcc_api_test.cfg` or Settings

2. **Flexible configuration:**
   - All parameters can be adjusted via command-line arguments
   - Uses standard configuration file if available

3. **Detailed results:**
   - JSON output for later analysis
   - Console output for immediate verification

## CI/CD Integration

The script can be integrated into CI/CD pipelines:

```bash
# In CI/CD Pipeline
python test/load_test_leaderboards.py --iterations 20 --output ci_load_test_results.json
if [ $? -ne 0 ]; then
    echo "Load test failed!"
    exit 1
fi
```

## Troubleshooting

**Problem: No devices/cyclists found**
- Check if devices and cyclists exist in the database
- Check if `is_visible=True` and `is_km_collection_enabled=True` are set

**Problem: API key error**
- Check if API keys were generated for devices
- Check the `mcc_api_test.cfg` file
- Check Django settings for `MCC_APP_API_KEY`

**Problem: Server not reachable**
- Ensure the Django server is running
- Check the `--base-url` parameter
- Check firewall settings
