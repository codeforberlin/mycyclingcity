# MyCyclingCity ESP32 Firmware

ESP32-based bicycle tachometer firmware for the MyCyclingCity project. This firmware tracks cycling distance and speed using pulse counting, identifies users via RFID tags, and transmits data to a backend server.

## Project Overview

The firmware runs on ESP32 microcontrollers and provides:

- **Pulse-based distance measurement** using ESP32's hardware PCNT (Pulse Counter) unit
- **RFID user identification** via MFRC522 reader
- **WiFi connectivity** for data transmission to backend server
- **OLED display** (optional) for real-time cycling data visualization
- **Deep sleep mode** for power efficiency when inactive
- **Web-based configuration** via captive portal (AP mode)
- **OTA update support** for remote firmware updates

## Supported Hardware

### Heltec WiFi LoRa 32 V3
- **Board**: `heltec_wifi_lora_32_V3`
- **Pulse Pin**: GPIO 2
- **LED Pin**: GPIO 35
- **OLED**: Integrated SSD1306 (128x64) via I2C
- **VEXT Pin**: GPIO 36 (OLED power control)
- **Buzzer Pin**: GPIO 14
- **RFID**: MFRC522 via SPI (SS: GPIO 5, RST: GPIO 26)

### Heltec WiFi LoRa 32 V2
- **Board**: `heltec_wifi_lora_32_V2`
- **Pulse Pin**: GPIO 13
- **LED Pin**: GPIO 25
- **OLED**: Integrated SSD1306 (128x64) via I2C (optional, enabled via `ENABLE_OLED`)
- **VEXT Pin**: GPIO 36 (OLED power control)
- **Buzzer Pin**: GPIO 14
- **RFID**: MFRC522 via SPI (SS: GPIO 5, RST: GPIO 26)

### Wemos D1 Mini32
- **Board**: `wemos_d1_mini32`
- **Pulse Pin**: GPIO 4
- **LED Pin**: GPIO 2
- **OLED**: External SSD1306 (128x64) via I2C (SDA: GPIO 21, SCL: GPIO 22)
- **Buzzer Pin**: GPIO 14
- **RFID**: MFRC522 via SPI (SS: GPIO 5, RST: GPIO 26)

## Hardware Requirements

### Pulse Sensor
- External 10 kΩ pull-up resistor to 3.3V for HIGH state
- 100 nF capacitor between ground and 3.3V
- **Note**: Internal software pull-up is insufficient as the pin goes LOW shortly after deep sleep, causing immediate wake-up

### RFID Reader
- MFRC522 module connected via SPI
- Default pins: SS (GPIO 5), RST (GPIO 26)

### Optional Components
- **OLED Display**: SSD1306 128x64 (I2C)
- **Active Buzzer**: Connected to BUZZER_PIN (GPIO 14)

## Building the Firmware

### Prerequisites
- [PlatformIO Core](https://platformio.org/install/cli) or PlatformIO IDE
- Python 3.7+ (for PlatformIO)

### Build Commands

```bash
# Build for Heltec WiFi LoRa 32 V3
pio run -e heltec_wifi_lora_32_V3

# Build for Heltec WiFi LoRa 32 V2
pio run -e heltec_wifi_lora_32_V2

# Build for Wemos D1 Mini32
pio run -e wemos_d1_mini32

# Build all environments
pio run
```

### Upload to Device

```bash
# Upload to connected device
pio run -e wemos_d1_mini32 -t upload

# Monitor serial output
pio device monitor -e wemos_d1_mini32
```

## Configuration

### Initial Setup

On first boot or when critical configuration is missing, the device enters **Configuration Mode**:

1. Device creates WiFi Access Point: `MCC_XXXX` (where XXXX is device MAC suffix)
2. Connect to AP (default password: none, or as configured)
3. Navigate to `http://192.168.4.1` in web browser
4. Configure:
   - WiFi SSID and password
   - Device name
   - Wheel circumference (cm)
   - Server URL
   - API authentication token
   - Data transmission interval

### Configuration Mode Exit

Configuration mode exits automatically:
- After 5 minutes (timeout)
- When a pulse is detected on the sensor pin (if not forced by missing config)

### Build-Time Defaults (Optional)

You can set default values in `platformio.ini` build flags:

```ini
-D DEFAULT_SERVER_URL=\"https://mycyclingcity.net\"
-D DEFAULT_API_KEY=\"your-api-key-here\"
```

These are only used if NVS (Non-Volatile Storage) is empty.

## Features

### Pulse Counting
- Uses ESP32 hardware PCNT unit for accurate pulse counting
- Configurable wheel circumference for distance calculation
- Real-time speed calculation based on interval measurements

### RFID User Identification
- Automatic user switching when new RFID tag is detected
- Distance counters reset on user change
- User ID lookup from backend server
- Visual/audio feedback on tag detection

### Data Transmission
- Periodic transmission of distance, speed, and pulse data
- JSON format via HTTP POST to `/api/update-data`
- Configurable transmission interval (default: 30 seconds)
- Automatic retry on connection failure

### Power Management
- Deep sleep mode after inactivity (default: 300 seconds)
- Wake-up on sensor pin LOW signal
- OLED display power management (Heltec boards)
- Automatic display sleep before deep sleep

### Test Mode
- Simulated data transmission for testing
- Configurable test distance and interval
- Overrides user ID tag with test identifier

## API Endpoints

The firmware communicates with the backend server via:

### Data Transmission

- **POST** `/api/update-data` - Send tachometer data
  ```json
  {
    "device_id": "MCC-Device_AB12",
    "id_tag": "a1b2c3d4",
    "distance": 0.105
  }
  ```

- **POST** `/api/get-user-id` - Retrieve username for RFID tag
  ```json
  {
    "id_tag": "a1b2c3d4"
  }
  ```
  Response:
  ```json
  {
    "user_id": "MaxMustermann"
  }
  ```

### Device Management

- **POST** `/api/device/config/report` - Report current device configuration to server
  ```json
  {
    "device_id": "MCC-Device_AB12",
    "config": {
      "device_name": "MCC-Device_AB12",
      "default_id_tag": "rfid001",
      "send_interval_seconds": 60,
      "wheel_size": 26,
      "server_url": "https://mycyclingcity.net",
      "api_key": "..."
    }
  }
  ```
  Response includes configuration differences if any.

- **GET** `/api/device/config/fetch?device_id=MCC-Device_AB12` - Fetch server-side configuration
  Response:
  ```json
  {
    "config": {
      "device_name": "MCC-Device_AB12",
      "default_id_tag": "rfid001",
      "send_interval_seconds": 60,
      "wheel_size": 26,
      "api_key": "...",
      "config_fetch_interval_seconds": 3600
    },
    "requires_restart": false
  }
  ```

- **GET** `/api/device/firmware/info?device_id=MCC-Device_AB12&current_version=1.0.0` - Check for firmware updates
  Response:
  ```json
  {
    "update_available": true,
    "latest_version": "1.1.0",
    "download_url": "/api/device/firmware/download?device_id=MCC-Device_AB12"
  }
  ```

- **GET** `/api/device/firmware/download?device_id=MCC-Device_AB12` - Download firmware binary
  Returns firmware binary file for OTA update.

- **POST** `/api/device/heartbeat` - Send heartbeat signal to indicate device is online
  ```json
  {
    "device_id": "MCC-Device_AB12"
  }
  ```
  Response:
  ```json
  {
    "success": true,
    "message": "Heartbeat received"
  }
  ```

**Note**: All device management endpoints require authentication via `X-Api-Key` header (device-specific or global API key).

## Dependencies

### Core Libraries
- **ArduinoJson** (^6.19.4) - JSON serialization/deserialization
- **MFRC522** (^1.4.12) - RFID reader library
- **U8g2** - OLED display library (for boards with display support)

### ESP32 Framework Libraries
- WiFi, WebServer, HTTPClient, Preferences (built-in)
- PCNT driver (hardware pulse counter)

## Development

### Project Structure

```
mcc-esp32/
├── src/
│   ├── main.cpp              # Main firmware code
│   ├── configserver.cpp/h   # Web configuration server
│   ├── rfid_mfrc522_control.cpp/h  # RFID reader module
│   └── led_control.cpp/h    # LED control utilities
├── test/
│   ├── test_main.cpp        # Unity test runner
│   ├── test_*.cpp           # Unit test files
│   └── mocks/               # Hardware mocks for testing
├── platformio.ini           # PlatformIO configuration
└── README.md                # This file
```

### Testing

See [test/README.md](test/README.md) for comprehensive testing documentation.

Run unit tests:
```bash
# Native tests (no hardware required)
pio test -e native

# ESP32 tests (requires hardware)
pio test -e wemos_d1_mini32_test
```

### CI/CD

The project includes a GitHub Actions workflow (`.github/workflows/mcc-esp32-ci.yml`) that:
- Builds all firmware environments
- Runs native unit tests
- Caches PlatformIO dependencies for faster builds

## Troubleshooting

### Device Not Entering Configuration Mode
- Ensure device is not waking from deep sleep (check wake-up reason)
- Verify critical configuration is missing (WiFi SSID, server URL, etc.)

### WiFi Connection Issues
- Check SSID and password in configuration
- Verify WiFi signal strength
- Some networks (e.g., Freifunk) may not require a password

### Pulse Counting Not Working
- Verify external pull-up resistor (10 kΩ) and capacitor (100 nF) are connected
- Check pulse pin configuration in `platformio.ini`
- Ensure sensor provides proper HIGH/LOW transitions

### OLED Display Issues
- Verify I2C connections (SDA/SCL pins)
- Check VEXT pin control (Heltec boards)
- Ensure `ENABLE_OLED` build flag is set if using display

## License

[Add license information here]

## Contributing

[Add contributing guidelines here]

## Support

For issues and questions, please open an issue in the project repository.

