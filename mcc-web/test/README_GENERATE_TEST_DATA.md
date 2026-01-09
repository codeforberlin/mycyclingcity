# Generate Live Test Kilometer Data

This script generates live test kilometer data via HTTP requests so that activities are visible for current devices and cyclists in the leaderboard.

## Prerequisites

1. **Django server must be running:**
   ```bash
   python manage.py runserver
   # or
   gunicorn config.wsgi:application --bind 127.0.0.1:8000
   ```

2. **Devices and cyclists must exist:**
   - At least one device (Device) in the database
   - At least one cyclist (Cyclist) with `id_tag` in the database

## Usage

### Basic Usage (10 updates, 5 second interval):
```bash
python test/generate_live_test_data.py
```

### With Options:
```bash
# 20 updates with 3 second interval
python test/generate_live_test_data.py --iterations 20 --interval 3

# Custom Base-URL
python test/generate_live_test_data.py --base-url http://localhost:8000
```

## Options

- `--iterations N`: Number of iterations (default: 10)
- `--interval SECONDS`: Interval between iterations in seconds (default: 5)
- `--base-url URL`: Base URL of the Django application (default: http://127.0.0.1:8000)

## What the Script Does

1. Reads all active devices and cyclists from the database
2. Sends HTTP POST requests to `/api/update-data` with:
   - `id_tag`: RFID tag of the cyclist
   - `device_id`: Name of the device
   - `distance`: Kilometer delta (0.1 to 2.0 km, random)
3. Shows success/error for each request
4. Generates a summary at the end

## Example Output

```
Found 3 active device(s)
Found 4 cyclist(s) with id_tag

Generating test data for 10 iterations with 5s interval...
============================================================

--- Iteration 1/10 ---
Device: device-01 (Device 01)
Cyclist: player-02 (ID Tag: tag-02)
Distance Delta: 1.23456 km
✅ Success: Update successful
Waiting 5 seconds...

--- Iteration 2/10 ---
...

============================================================
Summary:
  Successful updates: 10
  Failed updates: 0
  Total iterations: 10

✅ Test data generation completed!
   Check the leaderboard at: http://127.0.0.1:8000/de/map/
   Or the admin interface at: http://127.0.0.1:8000/de/admin/
```

## Troubleshooting

**Error: "No active devices found"**
- Create at least one device in the admin interface

**Error: "No cyclists with id_tag found"**
- Create at least one cyclist with `id_tag` in the admin interface

**Error: "HTTP 403: Invalid"**
- Check if `MCC_APP_API_KEY` is correctly set in settings

**Error: "Connection error"**
- Ensure the Django server is running
- Check the `--base-url` option
