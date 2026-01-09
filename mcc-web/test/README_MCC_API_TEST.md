# MCC API Test Script - Usage Guide

## Overview

The `mcc_api_test.py` script is a comprehensive testing tool for the MCC-DB Backend API. It supports various testing scenarios including single sends, continuous loops, and functional tests with validation.

## Prerequisites

1. **Configuration File**: `mcc_api_test.cfg` must be present in the test directory
2. **Python Dependencies**: `requests`, `configparser`, `argparse`
3. **Optional**: Django access for local database operations (when using `--create-test-data`)

## Configuration File

The script uses `mcc_api_test.cfg` for basic settings:

```ini
[general]
server_ip = 127.0.0.1
server_port = 8000
api_key = MCC-APP-API-KEY-SECRET
server_domain = api.mycyclingcity.net
auth_header_value = <base64-encoded-auth>
send_interval = 10
cyclist_duration = 60
```

## Basic Usage

### 1. Single Data Send

Send a single data point to the API:

```bash
python mcc_api_test.py --id_tag rfid001 --device mcc-demo01 --distance 0.5
```

### 2. Test get-user-id Endpoint

Query the user ID for a given ID tag:

```bash
python mcc_api_test.py --get-user-id --id_tag rfid001
```

### 3. Continuous Loop Mode

#### Simple Loop with Specific Values

```bash
python mcc_api_test.py --loop --id_tag rfid001 --device mcc-demo01 --distance 0.5
```

#### Loop with Simulated Distance

```bash
python mcc_api_test.py --loop --id_tag rfid001 --device mcc-demo01 --wheel-size 26
```

#### Loop with Fixed Speed

```bash
python mcc_api_test.py --loop --id_tag rfid001 --device mcc-demo01 --speed 15.0
```

### 4. Automated Test with Test Data File

#### Simple Test Data File Format

Create a JSON file (`test_data_simple.json`):

```json
{
  "devices": ["mcc-demo01", "mcc-test-001", "mcc-test-002"],
  "id_tags": ["rfid001", "rfid002", "rfid003"]
}
```

Run the loop:

```bash
python mcc_api_test.py --loop --test-data-file test_data_simple.json
```

#### Extended Test Data File Format

Create an extended JSON file (`test_data_extended.json`):

```json
{
  "cyclists": [
    {
      "id_tag": "rfid001",
      "target_km": 5.0
    },
    {
      "id_tag": "rfid002",
      "target_km": 3.5
    }
  ],
  "devices": [
    {
      "device_id": "mcc-demo01",
      "wheel_size": 26
    },
    {
      "device_id": "mcc-test-001",
      "wheel_size": 24
    }
  ],
  "device_switch_interval": 60,
  "send_interval": 10
}
```

## Functional Test Mode

The functional test mode runs a comprehensive test with validation:

### Basic Functional Test

```bash
python mcc_api_test.py --functional-test --test-data-file test_data_extended.json
```

### Functional Test with Duration

```bash
python mcc_api_test.py --functional-test --test-data-file test_data_extended.json --test-duration 300
```

### Functional Test with Custom Report File

```bash
python mcc_api_test.py --functional-test --test-data-file test_data_extended.json --report-file my_test_report.json
```

### Functional Test with Database Creation (Local Only)

When running locally with Django access, you can automatically create test data:

```bash
python mcc_api_test.py --functional-test --test-data-file test_data_extended.json --create-test-data
```

This will:
- Create cyclists in the database if they don't exist
- Create devices in the database if they don't exist
- Use existing data if already present

## Advanced Options

### Concurrent Connections

Limit the number of concurrent connections:

```bash
python mcc_api_test.py --loop --test-data-file test_data_simple.json --max-concurrent 5
```

### Device Limit

Limit the number of devices used:

```bash
python mcc_api_test.py --loop --test-data-file test_data_simple.json --max-devices 3
```

### Retry Configuration

Configure retry behavior:

```bash
python mcc_api_test.py --loop --test-data-file test_data_simple.json --retry-attempts 5 --retry-delay 2.0
```

### Send Jitter

Add random time offsets for realistic simulation:

```bash
python mcc_api_test.py --loop --test-data-file test_data_simple.json --send-jitter 1.0
```

### Custom Interval

Override the send interval:

```bash
python mcc_api_test.py --loop --test-data-file test_data_simple.json --interval 5
```

### Custom Cyclist Duration

Override the cyclist duration (device switch interval):

```bash
python mcc_api_test.py --loop --test-data-file test_data_simple.json --cyclist-duration 120
```

## Production/DNS Mode

Use DNS URL and Basic Auth for production:

```bash
python mcc_api_test.py --dns --loop --test-data-file test_data_simple.json
```

## Functional Test Features

The functional test mode includes:

1. **Parallel Data Sending**: Sends data for all cyclists simultaneously
2. **Device Switching**: Cyclists switch devices after a configurable interval
3. **Goal Tracking**: Tracks progress toward target kilometers for each cyclist
4. **API Validation**: Validates sent data against API responses
5. **Report Generation**: Creates detailed JSON reports with:
   - Test configuration
   - Cyclist results (sent km, goal reached, devices used)
   - Device results (total km sent, cyclists used)
   - Validation results (API comparison)
   - Summary statistics

## Report File Format

The generated report includes:

```json
{
  "test_info": {
    "start_time": "2025-01-15T10:00:00",
    "end_time": "2025-01-15T10:05:00",
    "duration_seconds": 300,
    "iterations": 30,
    "send_interval": 10,
    "device_switch_interval": 60
  },
  "test_config": {
    "cyclists": [...],
    "devices": [...]
  },
  "cyclist_results": {
    "rfid001": {
      "target_km": 5.0,
      "sent_km": 5.2,
      "goal_reached": true,
      "devices_used": ["mcc-demo01", "mcc-test-001"]
    }
  },
  "device_results": {...},
  "validation_results": {...},
  "summary": {
    "total_cyclists": 4,
    "goals_reached": 4,
    "total_km_sent": 18.5,
    "validations_passed": 4,
    "validations_failed": 0
  }
}
```

## Examples

### Example 1: Quick Single Test

```bash
python mcc_api_test.py --id_tag rfid001 --device mcc-demo01 --distance 1.0
```

### Example 2: Continuous Simulation

```bash
python mcc_api_test.py --loop --id_tag rfid001 --device mcc-demo01 --wheel-size 26 --interval 5
```

### Example 3: Full Functional Test

```bash
python mcc_api_test.py \
  --functional-test \
  --test-data-file test_data_extended_example.json \
  --create-test-data \
  --test-duration 600 \
  --report-file functional_test_report.json
```

### Example 4: Production Test

```bash
python mcc_api_test.py \
  --dns \
  --loop \
  --test-data-file test_data_simple.json \
  --max-concurrent 10 \
  --retry-attempts 5
```

## Notes

- When running locally with `--create-test-data`, the script will create test data in the database
- When running from a remote system, test data files are used directly
- The script automatically detects Django availability
- All German text has been translated to English
- The script uses "cyclist" terminology instead of "player"

## Troubleshooting

### Configuration File Not Found

Ensure `mcc_api_test.cfg` exists in the test directory or specify it with `--config`:

```bash
python mcc_api_test.py --config /path/to/config.cfg --id_tag rfid001 --device mcc-demo01 --distance 1.0
```

### Django Not Available

If you see warnings about Django not being available, the script will still work but won't be able to create database objects. Use test data files instead.

### API Connection Errors

Check:
- Server IP and port in configuration
- API key is correct
- Network connectivity
- Server is running

### Validation Failures

If validation fails in functional tests:
- Check API endpoint availability
- Verify data was actually sent
- Check for timing issues (wait longer before validation)
- Review the report file for detailed error messages

