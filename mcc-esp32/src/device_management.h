/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    device_management.h
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#ifndef DEVICE_MANAGEMENT_H
#define DEVICE_MANAGEMENT_H

#include <Arduino.h>
#include <ArduinoJson.h>

// API endpoint paths for device management
// Using static to avoid multiple definition errors when header is included in multiple files
static const char* API_DEVICE_CONFIG_REPORT_PATH = "/api/device/config/report";
static const char* API_DEVICE_CONFIG_FETCH_PATH = "/api/device/config/fetch";
static const char* API_DEVICE_HEARTBEAT_PATH = "/api/device/heartbeat";
static const char* API_DEVICE_FIRMWARE_INFO_PATH = "/api/device/firmware/info";
static const char* API_DEVICE_FIRMWARE_DOWNLOAD_PATH = "/api/device/firmware/download";

// Default firmware version (can be overridden by build flag)
#ifndef FIRMWARE_VERSION
#define FIRMWARE_VERSION "1.0.0"
#endif

// Timing constants
const unsigned long HEARTBEAT_INTERVAL_MS = 60000;  // 60 seconds
// Note: FIRMWARE_CHECK_INTERVAL_MS is used for internal timestamp tracking only.
// Firmware checks are performed:
// - After WiFi connection (in setup/connectToWiFi)
// - Before deep sleep (when no pulses detected)
// This avoids interrupting active pulse data collection.
const unsigned long FIRMWARE_CHECK_INTERVAL_MS = 120000;  // 2 minutes (for internal tracking only)

/**
 * @brief Reports current device configuration to the server.
 * 
 * Sends a POST request to /api/device/config/report with the current
 * device configuration from NVS. The server compares this with the
 * server-side configuration and reports any differences.
 * 
 * @return true if successful, false on error
 * 
 * @note Requires WiFi connection and valid serverUrl/authToken
 * @note Side effects: Sends HTTP request, writes to Serial
 */
bool reportDeviceConfig();

/**
 * @brief Fetches server-side configuration and applies it to the device.
 * 
 * Sends a GET request to /api/device/config/fetch to retrieve the
 * server-side configuration. If differences are detected, the configuration
 * is updated in NVS and the device may need to restart.
 * 
 * @return true if successful and config was fetched, false on error
 * 
 * @note Requires WiFi connection and valid serverUrl/authToken
 * @note Side effects: May modify NVS, writes to Serial
 */
bool fetchDeviceConfig();

/**
 * @brief Sends a heartbeat signal to the server.
 * 
 * Sends a POST request to /api/device/heartbeat to indicate the device
 * is alive and operational. This allows the server to monitor device health.
 * 
 * @return true if successful, false on error
 * 
 * @note Requires WiFi connection and valid serverUrl/authToken
 * @note Side effects: Sends HTTP request, writes to Serial
 */
bool sendHeartbeat();

/**
 * @brief Checks if a firmware update is available.
 * 
 * Sends a GET request to /api/device/firmware/info to check if a newer
 * firmware version is available on the server.
 * 
 * @return true if update is available, false if no update or on error
 * 
 * @note Requires WiFi connection and valid serverUrl/authToken
 * @note Side effects: Sends HTTP request, writes to Serial
 */
bool checkFirmwareUpdate();

/**
 * @brief Downloads and installs firmware update from the server.
 * 
 * Downloads firmware binary from /api/device/firmware/download and
 * installs it using ESP32 Update library. The device will restart
 * after successful installation.
 * 
 * @return true if successful, false on error
 * 
 * @note Requires WiFi connection and valid serverUrl/authToken
 * @note Side effects: Downloads firmware, writes to flash, restarts device
 * @warning This function will restart the device on success!
 */
bool downloadFirmware();

/**
 * @brief Gets the current firmware version.
 * 
 * Reads firmware version from NVS or returns default version.
 * 
 * @return String containing firmware version (e.g. "1.0.0")
 */
String getFirmwareVersion();

/**
 * @brief Initializes device management (loads timestamps from NVS).
 * 
 * Should be called during setup() to initialize device management
 * timestamps and configuration.
 */
void initDeviceManagement();

/**
 * @brief Checks if it's time to send heartbeat (based on interval).
 * 
 * @return true if heartbeat should be sent, false otherwise
 */
bool shouldSendHeartbeat();

/**
 * @brief Checks if it's time to check for firmware update (based on interval).
 * 
 * @return true if firmware check should be performed, false otherwise
 */
bool shouldCheckFirmware();

/**
 * @brief Tests if an API key works by making a test request to the server.
 * 
 * Tests the API key by making a lightweight request (e.g., heartbeat or config fetch)
 * to verify the key is valid before saving it to NVS.
 * 
 * @param testKey The API key to test
 * @return true if the key works (HTTP 200 or 403), false on error or invalid key
 * 
 * @note Requires WiFi connection and valid serverUrl
 * @note Side effects: Sends HTTP request, writes to Serial
 */
bool testApiKey(const String& testKey);

#endif // DEVICE_MANAGEMENT_H
