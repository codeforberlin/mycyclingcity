/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    device_management.cpp
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#include "device_management.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Update.h>
#include <Preferences.h>
#include <cmath>

// External global variables from main.cpp
extern Preferences preferences;
extern String serverUrl;
extern String apiKey;
extern String deviceName;
extern String deviceIdSuffix;
extern String idTag;
extern unsigned int sendInterval_sec;
extern float wheel_size;
extern bool debugEnabled;
extern String wifi_ssid;
extern String wifi_password;
extern bool testActive;
extern float testDistance;
extern unsigned int testInterval_sec;
extern unsigned long deepSleepTimeout_sec;
extern bool ledEnabled;
extern unsigned int configFetchInterval_sec;
extern unsigned long lastConfigFetchTime;
extern Preferences preferences;


// Internal state variables
static unsigned long lastHeartbeatTime = 0;
static unsigned long lastFirmwareCheckTime = 0;
static bool deviceManagementInitialized = false;
static String pendingFirmwareVersion = "";  // Store version from firmware/info response

/**
 * @brief Gets the current firmware version from NVS or returns default.
 */
String getFirmwareVersion() {
    // NVS key max length is 15 characters, so use shorter key
    String version = preferences.getString("fw_ver", "");
    if (version.length() == 0) {
        version = String(FIRMWARE_VERSION);
        // Store default version in NVS
        preferences.putString("fw_ver", version);
    }
    return version;
}

/**
 * @brief Initializes device management (loads timestamps from NVS).
 */
void initDeviceManagement() {
    if (deviceManagementInitialized) {
        return;
    }
    
    // Load last heartbeat and firmware check times from NVS
    // NVS key max length is 15 characters, so use shorter keys
    lastHeartbeatTime = preferences.getULong64("last_hb_time", 0);
    lastFirmwareCheckTime = preferences.getULong64("last_fw_chk", 0);
    
    // Initialize firmware version if not set
    getFirmwareVersion();
    
    deviceManagementInitialized = true;
    
    if (debugEnabled) {
        Serial.println("DEBUG: Device management initialized");
        Serial.printf("DEBUG: Firmware version: %s\n", getFirmwareVersion().c_str());
    }
}

/**
 * @brief Gets the AP password from NVS or returns default.
 * 
 * Helper function to read AP password from NVS (same logic as in configserver.cpp).
 * 
 * @return String AP password (minimum 8 characters, default if not set)
 */
String getAPPasswordFromNVS() {
    // NVS key max length is 15 characters, so use shorter key
    const char* DEFAULT_AP_PASSWORD = "mccmuims";
    String password = preferences.getString("ap_passwd", "");
    if (password.length() == 0 || password.length() < 8) {
        // Use default if not set or invalid (minimum 8 chars for WPA2)
        return String(DEFAULT_AP_PASSWORD);
    }
    return password;
}

/**
 * @brief Creates a JSON document with current device configuration.
 */
StaticJsonDocument<512> createConfigJson() {
    StaticJsonDocument<512> config;
    
    String finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += deviceIdSuffix;
    }
    
    config["device_name"] = finalDeviceId;
    config["default_id_tag"] = idTag;
    config["send_interval_seconds"] = sendInterval_sec;
    config["server_url"] = serverUrl;
    config["wifi_ssid"] = wifi_ssid;
    // Note: wifi_password is intentionally NOT sent for security
    config["debug_mode"] = debugEnabled;
    config["test_mode"] = testActive;
    config["deep_sleep_seconds"] = deepSleepTimeout_sec;
    config["wheel_size"] = wheel_size;
    // Note: apiKey/device_api_key is not part of config report (security)
    
    // Add config_fetch_interval_seconds
    config["config_fetch_interval_seconds"] = configFetchInterval_sec;
    
    // Add ap_password (read from NVS)
    String apPassword = getAPPasswordFromNVS();
    config["ap_password"] = apPassword;
    
    return config;
}

/**
 * @brief Reports current device configuration to the server.
 */
bool reportDeviceConfig() {
    // Turn on LED to indicate WiFi activity
    digitalWrite(LED_PIN, HIGH);
    
    if (serverUrl.length() == 0 || WiFi.status() != WL_CONNECTED) {
        digitalWrite(LED_PIN, LOW);  // Turn off LED on error
        if (debugEnabled) {
            Serial.println("DEBUG: reportDeviceConfig: No connection or configuration error.");
        }
        return false;
    }

    HTTPClient http;
    StaticJsonDocument<600> doc;
    
    String finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += deviceIdSuffix;
    }
    
    doc["device_id"] = finalDeviceId;
    doc["config"] = createConfigJson();

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    String finalUrl = serverUrl;
    if (finalUrl.endsWith("/")) {
        finalUrl.remove(finalUrl.length() - 1);
    }
    finalUrl += API_DEVICE_CONFIG_REPORT_PATH;

    if (debugEnabled) {
        Serial.print("DEBUG: Reporting device config to: ");
        Serial.println(finalUrl);
        Serial.println("DEBUG: Config JSON:");
        Serial.println(jsonPayload);
    }

    http.begin(finalUrl);
    http.addHeader("Content-Type", "application/json");
    if (apiKey.length() > 0) {
        http.addHeader("X-Api-Key", apiKey);
    }
    
    int httpCode = http.POST(jsonPayload);
    
    bool success = false;
    if (httpCode > 0) {
        if (httpCode == HTTP_CODE_OK) {
            String response = http.getString();
            if (debugEnabled) {
                Serial.println("DEBUG: Config report response:");
                Serial.println(response);
            }
            
            StaticJsonDocument<2000> responseDoc;  // Increased size for large responses with many differences
            DeserializationError error = deserializeJson(responseDoc, response);
            
            if (error && debugEnabled) {
                Serial.printf("DEBUG: Config report JSON parse error: %s\n", error.c_str());
            }
            
            if (!error && responseDoc.containsKey("success")) {
                success = responseDoc["success"].as<bool>();
                if (debugEnabled) {
                    Serial.printf("DEBUG: reportDeviceConfig() returning: %s\n", success ? "true" : "false");
                }
                
                // Check if there are differences
                if (responseDoc.containsKey("has_differences")) {
                    bool hasDiff = responseDoc["has_differences"].as<bool>();
                    if (hasDiff && debugEnabled) {
                        Serial.println("DEBUG: Configuration differences detected!");
                        if (responseDoc.containsKey("differences")) {
                            Serial.println("DEBUG: Differences:");
                            JsonArray diffs = responseDoc["differences"].as<JsonArray>();
                            for (JsonObject diff : diffs) {
                                Serial.printf("  - %s: server='%s', device='%s'\n",
                                    diff["field"].as<const char*>(),
                                    diff["server_value"].as<const char*>(),
                                    diff["device_value"].as<const char*>());
                            }
                        }
                    }
                }
            } else if (debugEnabled) {
                Serial.println("DEBUG: Config report response missing 'success' field or parse error");
            }
        } else {
            if (debugEnabled) {
                Serial.printf("DEBUG: Config report HTTP error: %d\n", httpCode);
                Serial.println(http.getString());
            }
        }
    } else {
        if (debugEnabled) {
            Serial.printf("DEBUG: Config report connection error: %s\n", http.errorToString(httpCode).c_str());
        }
    }

    http.end();
    digitalWrite(LED_PIN, LOW);  // Turn off LED after completion
    return success;
}

/**
 * @brief Fetches server-side configuration and applies it to the device.
 */
bool fetchDeviceConfig() {
    // Turn on LED to indicate WiFi activity
    digitalWrite(LED_PIN, HIGH);
    
    if (debugEnabled) {
        Serial.println("DEBUG: [fetchDeviceConfig] Starting...");
    }
    
    if (serverUrl.length() == 0 || WiFi.status() != WL_CONNECTED) {
        digitalWrite(LED_PIN, LOW);  // Turn off LED on error
        if (debugEnabled) {
            Serial.printf("DEBUG: [fetchDeviceConfig] No connection or configuration error. serverUrl.length()=%d, WiFi.status()=%d\n", 
                serverUrl.length(), WiFi.status());
        }
        return false;
    }

    HTTPClient http;
    
    String finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += deviceIdSuffix;
    }

    String finalUrl = serverUrl;
    if (finalUrl.endsWith("/")) {
        finalUrl.remove(finalUrl.length() - 1);
    }
    finalUrl += API_DEVICE_CONFIG_FETCH_PATH;
    finalUrl += "?device_id=" + finalDeviceId;

    if (debugEnabled) {
        Serial.print("DEBUG: [fetchDeviceConfig] Fetching device config from: ");
        Serial.println(finalUrl);
    }

    http.begin(finalUrl);
    http.addHeader("Content-Type", "application/json");
    if (apiKey.length() > 0) {
        http.addHeader("X-Api-Key", apiKey);
    }
    
    int httpCode = http.GET();
    
    if (debugEnabled) {
        Serial.printf("DEBUG: [fetchDeviceConfig] HTTP response code: %d\n", httpCode);
    }
    
    bool success = false;
    if (httpCode > 0) {
        if (httpCode == HTTP_CODE_OK) {
            String response = http.getString();
            if (debugEnabled) {
                Serial.println("DEBUG: [fetchDeviceConfig] Config fetch response:");
                Serial.println(response);
            }
            
            StaticJsonDocument<2000> responseDoc;  // Increased size for large config responses
            DeserializationError error = deserializeJson(responseDoc, response);
            
            if (error && debugEnabled) {
                Serial.printf("DEBUG: [fetchDeviceConfig] JSON parse error: %s\n", error.c_str());
            }
            
            if (!error && responseDoc.containsKey("success")) {
                success = responseDoc["success"].as<bool>();
                if (debugEnabled) {
                    Serial.printf("DEBUG: [fetchDeviceConfig] Response success: %s\n", success ? "true" : "false");
                }
                
                if (success && responseDoc.containsKey("config")) {
                    JsonObject config = responseDoc["config"].as<JsonObject>();
                    bool configChanged = false;
                    
                    if (debugEnabled) {
                        Serial.println("DEBUG: [Config Update] Starting configuration update from server...");
                        Serial.print("DEBUG: [Config Update] Received fields: ");
                        bool first = true;
                        for (JsonPair kv : config) {
                            if (!first) Serial.print(", ");
                            Serial.print(kv.key().c_str());
                            first = false;
                        }
                        Serial.println();
                    }
                    
                    // Note: device_name is only configurable via device WebGUI, not from server
                    // This ensures the device can always send data even if server config is missing
                    // The device_name from server config is ignored
                    
                    if (config.containsKey("default_id_tag")) {
                        String newTag = config["default_id_tag"].as<String>();
                        // Only update if server provides a real (non-empty) value
                        if (newTag.length() > 0) {
                            // Get current default from NVS (not from RAM, as RAM might have temporary RFID tag)
                            String currentDefault = preferences.getString("default_id_tag", "");
                            // Fallback to legacy "idTag" key for backward compatibility
                            if (currentDefault.length() == 0) {
                                currentDefault = preferences.getString("idTag", "");
                            }
                            
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] default_id_tag from server: %s, current default: %s\n", newTag.c_str(), currentDefault.c_str());
                            }
                            if (newTag != currentDefault) {
                                // Save as default_id_tag (not idTag) to distinguish from temporary RFID tag
                                preferences.putString("default_id_tag", newTag);
                                // Also update legacy "idTag" key for backward compatibility
                                preferences.putString("idTag", newTag);
                                // Only update global idTag if no RFID tag is currently active
                                // (We can't easily detect this, so we update it - RFID will override on next detection)
                                idTag = newTag;  // Update global variable
                                configChanged = true;
                                if (debugEnabled) {
                                    Serial.printf("DEBUG: [Config Update] default_id_tag updated to: %s\n", newTag.c_str());
                                }
                            } else if (debugEnabled) {
                                Serial.println("DEBUG: [Config Update] default_id_tag unchanged, no update needed");
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] default_id_tag from server is empty, ignoring (preserving device value)");
                        }
                    }
                    
                    if (config.containsKey("send_interval_seconds")) {
                        unsigned int newInterval = config["send_interval_seconds"].as<unsigned int>();
                        // Only update if server provides a real (non-zero) value
                        if (newInterval > 0) {
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] send_interval_seconds from server: %u, current: %u\n", newInterval, sendInterval_sec);
                            }
                            if (newInterval != sendInterval_sec) {
                                preferences.putUInt("sendInterval", newInterval);
                                sendInterval_sec = newInterval;  // Update global variable immediately
                                configChanged = true;
                                if (debugEnabled) {
                                    Serial.printf("DEBUG: [Config Update] send_interval_seconds updated to: %u\n", newInterval);
                                }
                            } else if (debugEnabled) {
                                Serial.println("DEBUG: [Config Update] send_interval_seconds unchanged, no update needed");
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] send_interval_seconds from server is 0, ignoring (preserving device value)");
                        }
                    }
                    
                    if (config.containsKey("server_url")) {
                        String newUrl = config["server_url"].as<String>();
                        // Only update if server provides a real (non-empty) value
                        if (newUrl.length() > 0) {
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] server_url from server: %s, current: %s\n", newUrl.c_str(), serverUrl.c_str());
                            }
                            if (newUrl != serverUrl) {
                                preferences.putString("serverUrl", newUrl);
                                serverUrl = newUrl;  // Update global variable immediately
                                configChanged = true;
                                if (debugEnabled) {
                                    Serial.printf("DEBUG: [Config Update] server_url updated to: %s\n", newUrl.c_str());
                                }
                            } else if (debugEnabled) {
                                Serial.println("DEBUG: [Config Update] server_url unchanged, no update needed");
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] server_url from server is empty, ignoring (preserving device value)");
                        }
                    }
                    
                    if (config.containsKey("wheel_size")) {
                        float newSizeMm = config["wheel_size"].as<float>();
                        // Server sends wheel_size directly in millimeters (circumference)
                        // Only update if server provides a valid value (500-3000 mm)
                        if (newSizeMm >= 500.0 && newSizeMm <= 3000.0) {
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] wheel_size from server: %.1f mm, current: %.1f mm\n", 
                                    newSizeMm, wheel_size);
                            }
                            if (abs(newSizeMm - wheel_size) > 1.0) {  // 1mm tolerance for comparison
                                preferences.putFloat("wheel_size", newSizeMm);
                                wheel_size = newSizeMm;  // Update global variable immediately
                                configChanged = true;
                                if (debugEnabled) {
                                    Serial.printf("DEBUG: [Config Update] wheel_size updated to: %.1f mm\n", newSizeMm);
                                }
                            } else if (debugEnabled) {
                                Serial.println("DEBUG: [Config Update] wheel_size unchanged, no update needed");
                            }
                        } else if (debugEnabled) {
                            Serial.printf("DEBUG: [Config Update] wheel_size from server is out of valid range (%.1f mm, expected 500-3000 mm), ignoring (preserving device value)\n", 
                                newSizeMm);
                        }
                    }
                    
                    // Note: debug_mode and test_mode are booleans, so they are always "real" values
                    // We check if the key exists, and if it does, we update (even if false)
                    if (config.containsKey("debug_mode")) {
                        bool newDebug = config["debug_mode"].as<bool>();
                        if (debugEnabled) {
                            Serial.printf("DEBUG: [Config Update] debug_mode from server: %s, current: %s\n", newDebug ? "true" : "false", debugEnabled ? "true" : "false");
                        }
                        if (newDebug != debugEnabled) {
                            preferences.putBool("debugEnabled", newDebug);
                            debugEnabled = newDebug;  // Update global variable immediately
                            configChanged = true;
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] debug_mode updated to: %s\n", newDebug ? "true" : "false");
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] debug_mode unchanged, no update needed");
                        }
                    }
                    
                    if (config.containsKey("test_mode")) {
                        bool newTest = config["test_mode"].as<bool>();
                        if (debugEnabled) {
                            Serial.printf("DEBUG: [Config Update] test_mode from server: %s, current: %s\n", newTest ? "true" : "false", testActive ? "true" : "false");
                        }
                        if (newTest != testActive) {
                            preferences.putBool("testModeEnabled", newTest);
                            testActive = newTest;  // Update global variable immediately
                            configChanged = true;
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] test_mode updated to: %s\n", newTest ? "true" : "false");
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] test_mode unchanged, no update needed");
                        }
                    }
                    
                    if (config.containsKey("deep_sleep_seconds")) {
                        unsigned long newSleep = config["deep_sleep_seconds"].as<unsigned long>();
                        // Note: 0 is a valid value for deep_sleep_seconds (means disabled)
                        // So we always update if the key exists, even if value is 0
                        // NVS key max length is 15 characters, so use shorter key
                        if (debugEnabled) {
                            Serial.printf("DEBUG: [Config Update] deep_sleep_seconds from server: %lu, current: %lu\n", newSleep, deepSleepTimeout_sec);
                        }
                        if (newSleep != deepSleepTimeout_sec) {
                            preferences.putUInt("deep_sleep", newSleep);  // Shortened key (max 15 chars)
                            deepSleepTimeout_sec = newSleep;  // Update global variable immediately
                            configChanged = true;
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] deep_sleep_seconds updated to: %lu\n", newSleep);
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] deep_sleep_seconds unchanged, no update needed");
                        }
                    }
                    
                    if (config.containsKey("ap_password")) {
                        String newAPPassword = config["ap_password"].as<String>();
                        // Only update if server provides a real (non-empty, min 8 chars) value
                        if (newAPPassword.length() >= 8) {
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] ap_password from server: %s\n", newAPPassword.c_str());
                                String currentAPPassword = preferences.getString("ap_passwd", "");
                                Serial.printf("DEBUG: [Config Update] Current AP password in NVS: %s\n", currentAPPassword.length() > 0 ? currentAPPassword.c_str() : "(empty/default)");
                            }
                            String currentAPPassword = preferences.getString("ap_passwd", "");
                            if (newAPPassword != currentAPPassword) {
                                preferences.putString("ap_passwd", newAPPassword);
                                configChanged = true;
                                if (debugEnabled) {
                                    Serial.printf("DEBUG: [Config Update] ap_password updated to: %s (restart required)\n", newAPPassword.c_str());
                                }
                            } else if (debugEnabled) {
                                Serial.println("DEBUG: [Config Update] ap_password unchanged, no update needed");
                            }
                        } else if (debugEnabled) {
                            if (newAPPassword.length() > 0) {
                                Serial.printf("DEBUG: [Config Update] ap_password from server too short (min 8 chars), ignoring (preserving device value): %s\n", newAPPassword.c_str());
                            } else {
                                Serial.println("DEBUG: [Config Update] ap_password from server is empty, ignoring (preserving device value)");
                            }
                        }
                    }
                    
                    // Note: wifi_ssid and wifi_password are typically not updated remotely for security
                    
                    // Handle device_api_key from server - test before saving
                    if (config.containsKey("device_api_key")) {
                        String newApiKey = config["device_api_key"].as<String>();
                        // Only update if server provides a real (non-empty) value
                        if (newApiKey.length() > 0) {
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] device_api_key received from server: %s\n", newApiKey.c_str());
                                Serial.printf("DEBUG: [Config Update] Current API key in NVS: %s\n", apiKey.length() > 0 ? apiKey.c_str() : "(empty/default)");
                            }
                            
                            // Test the new API key before saving it
                            if (testApiKey(newApiKey)) {
                                // New key works, save it to NVS
                                preferences.putString("apiKey", newApiKey);
                                apiKey = newApiKey;
                                configChanged = true;
                                if (debugEnabled) {
                                    Serial.printf("DEBUG: [Config Update] device_api_key updated to: %s (tested successfully)\n", newApiKey.c_str());
                                }
                            } else {
                                // New key doesn't work, keep current key
                                if (debugEnabled) {
                                    Serial.println("DEBUG: [Config Update] device_api_key from server failed test, keeping current key");
                                }
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] device_api_key from server is empty, ignoring (preserving device value)");
                        }
                    }
                    
                    // Handle config_fetch_interval_seconds from server
                    if (config.containsKey("config_fetch_interval_seconds")) {
                        unsigned int newInterval = config["config_fetch_interval_seconds"].as<unsigned int>();
                        // Only update if server provides a real (non-zero) value
                        if (newInterval > 0) {
                            if (debugEnabled) {
                                Serial.printf("DEBUG: [Config Update] config_fetch_interval_seconds from server: %u, current: %u\n", newInterval, configFetchInterval_sec);
                            }
                            if (newInterval != configFetchInterval_sec) {
                                // NVS key max length is 15 characters, so use shorter key
                                preferences.putUInt("cfg_fetch_int", newInterval);
                                configFetchInterval_sec = newInterval;  // Update global variable immediately
                                configChanged = true;
                                if (debugEnabled) {
                                    Serial.printf("DEBUG: [Config Update] config_fetch_interval_seconds updated to: %u\n", newInterval);
                                }
                            } else if (debugEnabled) {
                                Serial.println("DEBUG: [Config Update] config_fetch_interval_seconds unchanged, no update needed");
                            }
                        } else if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] config_fetch_interval_seconds from server is 0, ignoring (preserving device value)");
                        }
                    }
                    
                    if (configChanged) {
                        if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] Configuration updated from server. Restart recommended.");
                        }
                        // Note: We don't auto-restart here, let the user decide or restart manually
                    } else {
                        if (debugEnabled) {
                            Serial.println("DEBUG: [Config Update] Configuration is already in sync - no changes needed.");
                        }
                    }
                }
            }
        } else {
            if (debugEnabled) {
                Serial.printf("DEBUG: [fetchDeviceConfig] HTTP error: %d\n", httpCode);
                String errorResponse = http.getString();
                Serial.print("DEBUG: [fetchDeviceConfig] Error response: ");
                Serial.println(errorResponse);
            }
        }
    } else {
        if (debugEnabled) {
            Serial.printf("DEBUG: [fetchDeviceConfig] Connection error: %s\n", http.errorToString(httpCode).c_str());
        }
    }

    http.end();
    digitalWrite(LED_PIN, LOW);  // Turn off LED after completion
    if (debugEnabled) {
        Serial.printf("DEBUG: [fetchDeviceConfig] Returning: %s\n", success ? "true" : "false");
    }
    return success;
}

/**
 * @brief Sends a heartbeat signal to the server.
 */
bool sendHeartbeat() {
    // Turn on LED to indicate WiFi activity
    digitalWrite(LED_PIN, HIGH);
    
    if (serverUrl.length() == 0 || WiFi.status() != WL_CONNECTED) {
        digitalWrite(LED_PIN, LOW);  // Turn off LED on error
        if (debugEnabled) {
            Serial.println("DEBUG: sendHeartbeat: No connection or configuration error.");
        }
        return false;
    }

    HTTPClient http;
    StaticJsonDocument<200> doc;
    
    String finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += deviceIdSuffix;
    }
    
    doc["device_id"] = finalDeviceId;

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    String finalUrl = serverUrl;
    if (finalUrl.endsWith("/")) {
        finalUrl.remove(finalUrl.length() - 1);
    }
    finalUrl += API_DEVICE_HEARTBEAT_PATH;

    if (debugEnabled) {
        Serial.print("DEBUG: Sending heartbeat to: ");
        Serial.println(finalUrl);
    }

    http.begin(finalUrl);
    http.addHeader("Content-Type", "application/json");
    if (apiKey.length() > 0) {
        http.addHeader("X-Api-Key", apiKey);
    }
    
    int httpCode = http.POST(jsonPayload);
    
    bool success = false;
    if (httpCode > 0) {
        if (httpCode == HTTP_CODE_OK) {
            String response = http.getString();
            if (debugEnabled) {
                Serial.println("DEBUG: Heartbeat response:");
                Serial.println(response);
            }
            
            StaticJsonDocument<200> responseDoc;
            DeserializationError error = deserializeJson(responseDoc, response);
            
            if (!error && responseDoc.containsKey("success")) {
                success = responseDoc["success"].as<bool>();
                
                // Update last heartbeat time
                lastHeartbeatTime = millis();
                preferences.putULong64("last_hb_time", lastHeartbeatTime);
            }
        } else {
            if (debugEnabled) {
                Serial.printf("DEBUG: Heartbeat HTTP error: %d\n", httpCode);
            }
        }
    } else {
        if (debugEnabled) {
            Serial.printf("DEBUG: Heartbeat connection error: %s\n", http.errorToString(httpCode).c_str());
        }
    }

    http.end();
    digitalWrite(LED_PIN, LOW);  // Turn off LED after completion
    return success;
}

/**
 * @brief Checks if a firmware update is available.
 */
bool checkFirmwareUpdate() {
    // Turn on LED to indicate WiFi activity
    digitalWrite(LED_PIN, HIGH);
    
    if (serverUrl.length() == 0 || WiFi.status() != WL_CONNECTED) {
        digitalWrite(LED_PIN, LOW);  // Turn off LED on error
        if (debugEnabled) {
            Serial.println("DEBUG: checkFirmwareUpdate: No connection or configuration error.");
        }
        return false;
    }

    HTTPClient http;
    
    String finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += deviceIdSuffix;
    }
    
    String currentVersion = getFirmwareVersion();

    String finalUrl = serverUrl;
    if (finalUrl.endsWith("/")) {
        finalUrl.remove(finalUrl.length() - 1);
    }
    finalUrl += API_DEVICE_FIRMWARE_INFO_PATH;
    finalUrl += "?device_id=" + finalDeviceId;
    finalUrl += "&current_version=" + currentVersion;

    if (debugEnabled) {
        Serial.print("DEBUG: Checking firmware update from: ");
        Serial.println(finalUrl);
    }

    http.begin(finalUrl);
    http.addHeader("Content-Type", "application/json");
    if (apiKey.length() > 0) {
        http.addHeader("X-Api-Key", apiKey);
    }
    
    int httpCode = http.GET();
    
    bool updateAvailable = false;
    if (httpCode > 0) {
        if (httpCode == HTTP_CODE_OK) {
            String response = http.getString();
            if (debugEnabled) {
                Serial.println("DEBUG: Firmware info response:");
                Serial.println(response);
            }
            
            // Increase JSON document size to handle full firmware info response
            // Response includes: success, update_available, current_version, available_version,
            // firmware_name, file_size, checksum_md5, download_url, message
            StaticJsonDocument<800> responseDoc;
            DeserializationError error = deserializeJson(responseDoc, response);
            
            if (error) {
                if (debugEnabled) {
                    Serial.printf("DEBUG: JSON parse error: %s\n", error.c_str());
                }
            } else {
                if (debugEnabled) {
                    Serial.println("DEBUG: JSON parsed successfully");
                }
                
                if (responseDoc.containsKey("success")) {
                    bool success = responseDoc["success"].as<bool>();
                    
                    if (debugEnabled) {
                        Serial.printf("DEBUG: Parsed success: %s\n", success ? "true" : "false");
                        Serial.printf("DEBUG: Has update_available key: %s\n", 
                            responseDoc.containsKey("update_available") ? "true" : "false");
                    }
                    
                    if (success && responseDoc.containsKey("update_available")) {
                        updateAvailable = responseDoc["update_available"].as<bool>();
                        
                        if (debugEnabled) {
                            Serial.printf("DEBUG: Parsed update_available: %s\n", updateAvailable ? "true" : "false");
                        }
                        
                        if (updateAvailable) {
                            // Store the available version for later use after successful update
                            if (responseDoc.containsKey("available_version")) {
                                pendingFirmwareVersion = responseDoc["available_version"].as<String>();
                                if (debugEnabled) {
                                    Serial.println("DEBUG: Firmware update available!");
                                    Serial.printf("DEBUG: Available version: %s\n", pendingFirmwareVersion.c_str());
                                }
                            } else {
                                if (debugEnabled) {
                                    Serial.println("DEBUG: Firmware update available, but version not in response!");
                                }
                            }
                        } else {
                            pendingFirmwareVersion = "";  // Clear pending version if no update
                            if (debugEnabled) {
                                Serial.println("DEBUG: Firmware is up to date.");
                            }
                        }
                    } else {
                        if (debugEnabled) {
                            Serial.println("DEBUG: Response missing 'success' or 'update_available' field");
                            if (!success) {
                                Serial.println("DEBUG: success field is false");
                            }
                            if (!responseDoc.containsKey("update_available")) {
                                Serial.println("DEBUG: update_available key not found in response");
                            }
                        }
                    }
                } else {
                    if (debugEnabled) {
                        Serial.println("DEBUG: Response does not contain 'success' field");
                    }
                }
            }
        } else {
            if (debugEnabled) {
                Serial.printf("DEBUG: Firmware info HTTP error: %d\n", httpCode);
                Serial.println(http.getString());
            }
        }
    } else {
        if (debugEnabled) {
            Serial.printf("DEBUG: Firmware info connection error: %s\n", http.errorToString(httpCode).c_str());
        }
    }

    http.end();
    
    // Update last firmware check time
    // NVS key max length is 15 characters, so use shorter key
    lastFirmwareCheckTime = millis();
    preferences.putULong64("last_fw_chk", lastFirmwareCheckTime);
    
    digitalWrite(LED_PIN, LOW);  // Turn off LED after completion
    return updateAvailable;
}

/**
 * @brief Downloads and installs firmware update from the server.
 */
bool downloadFirmware() {
    // Turn on LED to indicate WiFi activity
    digitalWrite(LED_PIN, HIGH);
    
    if (serverUrl.length() == 0 || WiFi.status() != WL_CONNECTED) {
        digitalWrite(LED_PIN, LOW);  // Turn off LED on error
        if (debugEnabled) {
            Serial.println("DEBUG: downloadFirmware: No connection or configuration error.");
        }
        return false;
    }

    HTTPClient http;
    
    String finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += deviceIdSuffix;
    }

    String finalUrl = serverUrl;
    if (finalUrl.endsWith("/")) {
        finalUrl.remove(finalUrl.length() - 1);
    }
    finalUrl += API_DEVICE_FIRMWARE_DOWNLOAD_PATH;
    finalUrl += "?device_id=" + finalDeviceId;

    if (debugEnabled) {
        Serial.print("DEBUG: Downloading firmware from: ");
        Serial.println(finalUrl);
    }

    http.begin(finalUrl);
    if (apiKey.length() > 0) {
        http.addHeader("X-Api-Key", apiKey);
    }
    
    int httpCode = http.GET();
    
    if (httpCode > 0) {
        if (httpCode == HTTP_CODE_OK) {
            // Get content length
            int contentLength = http.getSize();
            if (debugEnabled) {
                Serial.printf("DEBUG: Firmware size: %d bytes\n", contentLength);
            }
            
            if (contentLength > 0) {
                // Begin update
                        if (!Update.begin(contentLength)) {
                            digitalWrite(LED_PIN, LOW);  // Turn off LED on error
                            if (debugEnabled) {
                                Serial.println("DEBUG: Update.begin() failed!");
                                Update.printError(Serial);
                            }
                            http.end();
                            return false;
                        }
                
                // Download and write firmware in chunks
                WiFiClient* stream = http.getStreamPtr();
                uint8_t buffer[512];
                size_t written = 0;
                
                while (http.connected() && (written < contentLength)) {
                    size_t available = stream->available();
                    if (available) {
                        size_t toRead = (available > sizeof(buffer)) ? sizeof(buffer) : available;
                        size_t bytesRead = stream->readBytes(buffer, toRead);
                        
                        if (Update.write(buffer, bytesRead) != bytesRead) {
                            digitalWrite(LED_PIN, LOW);  // Turn off LED on error
                            if (debugEnabled) {
                                Serial.println("DEBUG: Update.write() failed!");
                                Update.printError(Serial);
                            }
                            Update.abort();
                            http.end();
                            return false;
                        }
                        
                        written += bytesRead;
                        
                        if (debugEnabled && (written % 10240 == 0)) {
                            Serial.printf("DEBUG: Downloaded %d / %d bytes\n", written, contentLength);
                        }
                    }
                    delay(1);
                }
                
                // End update
                if (Update.end()) {
                    if (Update.isFinished()) {
                        // Update firmware version in NVS before restart
                        // Use version from firmware/info response if available, otherwise try to get from header
                        String newVersion = pendingFirmwareVersion;
                        if (newVersion.length() == 0) {
                            // Try to get version from response header
                            String headerVersion = http.header("X-Firmware-Version");
                            if (headerVersion.length() > 0) {
                                newVersion = headerVersion;
                            }
                        }
                        
                        if (newVersion.length() > 0) {
                            // NVS key max length is 15 characters, so use shorter key
                            preferences.putString("fw_ver", newVersion);
                            if (debugEnabled) {
                                Serial.printf("DEBUG: Updated firmware version in NVS: %s\n", newVersion.c_str());
                            }
                        } else {
                            if (debugEnabled) {
                                Serial.println("DEBUG: Warning: Could not determine new firmware version!");
                            }
                        }
                        
                        if (debugEnabled) {
                            Serial.println("DEBUG: Firmware update successful! Restarting...");
                        }
                        http.end();
                        delay(1000);
                        ESP.restart();
                        return true; // This will never be reached, but compiler is happy
                    } else {
                        digitalWrite(LED_PIN, LOW);  // Turn off LED on error
                        if (debugEnabled) {
                            Serial.println("DEBUG: Update not finished!");
                        }
                        Update.abort();
                    }
                } else {
                    digitalWrite(LED_PIN, LOW);  // Turn off LED on error
                    if (debugEnabled) {
                        Serial.println("DEBUG: Update.end() failed!");
                        Update.printError(Serial);
                    }
                }
            } else {
                digitalWrite(LED_PIN, LOW);  // Turn off LED on error
                if (debugEnabled) {
                    Serial.println("DEBUG: Invalid firmware size!");
                }
            }
        } else {
            digitalWrite(LED_PIN, LOW);  // Turn off LED on error
            if (debugEnabled) {
                Serial.printf("DEBUG: Firmware download HTTP error: %d\n", httpCode);
                String response = http.getString();
                Serial.println(response);
            }
        }
    } else {
        digitalWrite(LED_PIN, LOW);  // Turn off LED on error
        if (debugEnabled) {
            Serial.printf("DEBUG: Firmware download connection error: %s\n", http.errorToString(httpCode).c_str());
        }
    }

    http.end();
    digitalWrite(LED_PIN, LOW);  // Turn off LED after completion (or error)
    return false;
}

/**
 * @brief Tests if an API key works by making a test request to the server.
 * 
 * Tests the API key by making a lightweight heartbeat request to verify
 * the key is valid before saving it to NVS.
 */
bool testApiKey(const String& testKey) {
    if (testKey.length() == 0 || serverUrl.length() == 0 || WiFi.status() != WL_CONNECTED) {
        if (debugEnabled) {
            Serial.println("DEBUG: [testApiKey] Cannot test: no key, no server URL, or no WiFi connection");
        }
        return false;
    }

    HTTPClient http;
    
    String finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += deviceIdSuffix;
    }

    // Use heartbeat endpoint for testing (lightweight request)
    String finalUrl = serverUrl;
    if (finalUrl.endsWith("/")) {
        finalUrl.remove(finalUrl.length() - 1);
    }
    finalUrl += API_DEVICE_HEARTBEAT_PATH;

    if (debugEnabled) {
        Serial.print("DEBUG: [testApiKey] Testing API key with heartbeat request to: ");
        Serial.println(finalUrl);
    }

    http.begin(finalUrl);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Api-Key", testKey);
    
    // Create minimal JSON payload
    StaticJsonDocument<100> doc;
    doc["device_id"] = finalDeviceId;
    String jsonPayload;
    serializeJson(doc, jsonPayload);
    
    int httpCode = http.POST(jsonPayload);
    
    bool success = false;
    if (httpCode > 0) {
        // Only HTTP 200 (OK) means the API key is valid and works
        // HTTP 401/403 means unauthorized/forbidden (key is invalid)
        // Other codes mean server error or unexpected response
        if (httpCode == HTTP_CODE_OK) {
            success = true;
            if (debugEnabled) {
                Serial.printf("DEBUG: [testApiKey] API key test successful (HTTP %d) - key is valid\n", httpCode);
            }
        } else if (httpCode == 401 || httpCode == 403) {
            if (debugEnabled) {
                Serial.printf("DEBUG: [testApiKey] API key test failed: Unauthorized/Forbidden (HTTP %d) - key is invalid\n", httpCode);
            }
            success = false;
        } else {
            if (debugEnabled) {
                Serial.printf("DEBUG: [testApiKey] API key test returned unexpected HTTP code: %d - keeping current key\n", httpCode);
            }
            // For other codes, we're conservative and don't update (server error, etc.)
            success = false;
        }
    } else {
        if (debugEnabled) {
            Serial.printf("DEBUG: [testApiKey] API key test connection error: %s - keeping current key\n", http.errorToString(httpCode).c_str());
        }
        success = false;
    }

    http.end();
    return success;
}

/**
 * @brief Checks if it's time to send heartbeat (based on interval).
 */
bool shouldSendHeartbeat() {
    if (!deviceManagementInitialized) {
        return false;
    }
    unsigned long now = millis();
    // Handle millis() overflow (happens after ~49 days)
    if (now < lastHeartbeatTime) {
        lastHeartbeatTime = 0;
    }
    return (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS);
}

/**
 * @brief Checks if it's time to check for firmware update (based on interval).
 */
bool shouldCheckFirmware() {
    if (!deviceManagementInitialized) {
        return false;
    }
    unsigned long now = millis();
    // Handle millis() overflow
    if (now < lastFirmwareCheckTime) {
        lastFirmwareCheckTime = 0;
    }
    return (now - lastFirmwareCheckTime >= FIRMWARE_CHECK_INTERVAL_MS);
}
