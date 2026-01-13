# MyCyclingCity

A hardware-software ecosystem for cycling infrastructure tracking that combines ESP32-based tachometers with a Django web application to track cycling activities, manage groups, and display real-time leaderboards.

## Project Overview

MyCyclingCity is a comprehensive cycling tracking platform that uses ESP32-based tachometers to measure cycling distance via pulse counting. The system identifies users via RFID tags and transmits data to a Django backend for real-time visualization, leaderboards, and game-based challenges.

### Key Features

- **Hardware Integration**: ESP32-based tachometers with pulse counting, RFID identification, and WiFi connectivity
- **Real-time Tracking**: Live map visualization with OSM/Leaflet integration
- **Gamification**: Kilometer challenges and leaderboards
- **Multi-device Support**: Heltec WiFi LoRa 32 V3, V2, and Wemos D1 Mini32
- **Web-based Configuration**: Captive portal for device setup
- **OTA Updates**: Remote firmware updates

## Repository Structure

This is a **mono-repository** containing two main sub-projects:

### [mcc-esp32](mcc-esp32/)

ESP32 firmware for bicycle tachometers. Built with PlatformIO, supports multiple hardware platforms, and includes comprehensive unit testing.

**See [mcc-esp32/README.md](mcc-esp32/README.md) for detailed documentation.**

### [mcc-web](mcc-web/)

Django web application providing the backend API, admin interface, map visualization, leaderboards, and game functionality.

**See [mcc-web/README.md](mcc-web/README.md) for detailed documentation.**

## CI/CD Status

The project includes GitHub Actions integration for automated testing and building:

- **ESP32 Firmware CI**: Automatically builds all firmware environments and runs unit tests on push/PR
  - Workflow: `.github/workflows/mcc-esp32-ci.yml`
  - Builds: Heltec V3, Heltec V2, Wemos D1 Mini32
  - Tests: Native unit tests (no hardware required)

## Quick Start

### ESP32 Firmware

```bash
cd mcc-esp32
pio run -e heltec_wifi_lora_32_V3
```

### Web Application

```bash
cd mcc-web
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Documentation

- [ESP32 Firmware Documentation](mcc-esp32/README.md)
- [Web Application Documentation](mcc-web/README.md)
- [API Reference](mcc-web/docs/api_reference.md)

## Contributing

All code, comments, and documentation must be in English.

## 🤖 AI Transparency

This project embraces modern development workflows. Parts of the codebase, documentation, and logic in mcc-web and mcc-esp32 have been generated or optimized with the assistance of Artificial Intelligence (LLMs like Gemini and Cursor). All AI-assisted contributions are reviewed and maintained by the MyCyclingCity project team.

## License

Copyright (c) 2026 SAI-Lab / MyCyclingCity

This project is licensed under multiple open-source licenses:

- **mcc-web**: Licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](mcc-web/LICENSE)
- **mcc-esp32**: Licensed under the [GNU General Public License v3.0 (GPL-3.0)](mcc-esp32/LICENSE)

For the full license texts, please refer to:
- [mcc-web/LICENSE](mcc-web/LICENSE) - AGPL-3.0
- [mcc-esp32/LICENSE](mcc-esp32/LICENSE) - GPL-3.0
- [Root LICENSE](LICENSE) - License overview
