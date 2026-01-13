# Project Dependencies

This document provides a comprehensive overview of all dependencies used in the mcc-esp32 project, including their versions and licenses.

## Direct Dependencies

| Library Name | Version | License | Notes |
|--------------|---------|---------|-------|
| ArduinoJson | 6.19.4 | MIT | JSON processing library |
| U8g2 | latest | BSD-2-Clause | OLED display library (SSD1306) |
| **MFRC522** | **1.4.12** | **GPL-2.0** | **RFID reader library** ⚠️ |
| ESP32 Platform | latest | Apache-2.0 | ESP32 microcontroller platform |
| Arduino Framework | latest | LGPL-2.1 | Embedded development framework |
| Unity Test Framework | latest | MIT | Unit testing framework (test only) |

## License Summary

### Permissive Licenses (No Restrictions)

The following dependencies use permissive licenses that allow commercial use, modification, and distribution:

- **MIT License** (2 packages):
  - ArduinoJson
  - Unity Test Framework

- **Apache-2.0** (1 package):
  - ESP32 Platform

- **BSD-2-Clause** (1 package):
  - U8g2

### Copyleft Licenses (Require Attention)

- **LGPL-2.1** (1 package):
  - Arduino Framework
  - Note: LGPL allows linking with proprietary code, but modifications to the framework itself must be released under LGPL.

- **GPL-2.0** (1 package):
  - **MFRC522** ⚠️ **RESTRICTIVE LICENSE**

## License Compliance

### ⚠️ Restrictive Licenses

**WARNING: The following library uses a restrictive copyleft license:**

#### MFRC522 (GPL-2.0)

- **Library**: MFRC522
- **Version**: 1.4.12
- **License**: GNU General Public License v2.0 (GPL-2.0)
- **Owner**: miguelbalboa
- **Purpose**: RFID reader library for MFRC522 module

**License Implications:**

The GPL-2.0 license is a strong copyleft license that requires:

1. **Source Code Disclosure**: If you distribute the software, you must provide the complete source code of your application, including any modifications to the MFRC522 library.

2. **Derivative Works**: Any work that uses GPL-2.0 licensed code must also be licensed under GPL-2.0.

3. **Commercial Use**: While GPL-2.0 allows commercial use, it requires that the entire application be open-sourced if distributed.

**Recommendations:**

- If this project is intended for commercial distribution, consider:
  - Finding an alternative RFID library with a more permissive license (MIT, BSD, Apache-2.0)
  - Contacting the library maintainer to discuss licensing options
  - Ensuring compliance with GPL-2.0 requirements if continuing to use MFRC522

- If this project is open-source and will be distributed under GPL-2.0, ensure all other components are compatible with GPL-2.0.

### LGPL-2.1 License (Arduino Framework)

The Arduino Framework uses LGPL-2.1, which is less restrictive than GPL:

- **Linking**: You can link LGPL libraries with proprietary code
- **Modifications**: If you modify the framework itself, you must release those modifications under LGPL-2.1
- **Distribution**: You must provide the source code of the LGPL-licensed framework when distributing

## Additional Information

- **SBOM Format**: CycloneDX JSON (version 1.5)
- **SBOM Location**: `sbom.json` in the project root
- **Build System**: PlatformIO
- **Last Updated**: 2025-01-27
- **Source**: Generated from `platformio.ini`

## Notes

- **U8g2 version**: The project uses `olikraus/U8g2` without a specific version constraint, so the latest version is used at build time.
- **Platform versions**: ESP32 platform and Arduino framework versions are determined by PlatformIO at build time.
- **Test dependencies**: Unity test framework is only used in test environments (`env:native`, `env:wemos_d1_mini32_test`) and is not included in production builds.
- **Transitive dependencies**: This list includes only direct dependencies. PlatformIO may include additional transitive dependencies during the build process.

## Board-Specific Dependencies

The project supports multiple ESP32 boards with different dependency configurations:

- **Heltec WiFi LoRa 32 V3**: ArduinoJson, U8g2, MFRC522
- **Heltec WiFi LoRa 32 V2**: ArduinoJson, MFRC522 (OLED support via build flags)
- **Wemos D1 Mini32**: ArduinoJson, MFRC522, U8g2@^2.35.9
