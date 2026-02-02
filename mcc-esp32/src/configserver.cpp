/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    configserver.cpp
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#include "configserver.h"
#include <WiFi.h>
#include <Update.h>

#ifdef ENABLE_OLED
extern void display_FirmwareUpdate();
#endif

// --- Configuration ---
// SSID and password for configuration access point
// Default password (used if not set in NVS)
const char* DEFAULT_AP_PASSWORD = "mccmuims";

/**
 * @brief Gets the AP password from NVS or returns default.
 * 
 * @return String AP password (minimum 8 characters, default if not set)
 */
String getAPPassword() {
    // NVS key max length is 15 characters, so use shorter key
    String password = preferences.getString("ap_passwd", "");
    if (password.length() == 0 || password.length() < 8) {
        // Use default if not set or invalid (minimum 8 chars for WPA2)
        if (debugEnabled) {
            Serial.printf("DEBUG: Using default AP password: %s\n", DEFAULT_AP_PASSWORD);
        }
        return String(DEFAULT_AP_PASSWORD);
    }
    if (debugEnabled) {
        Serial.printf("DEBUG: AP password loaded from NVS: %s\n", password.c_str());
    }
    return password;
}

// HTML configuration form
const char* HTML_FORM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<title>ESP32 Bike Tacho Konfiguration</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta charset="UTF-8"> <style>
  body{font-family:Arial,sans-serif;margin:auto;max-width:600px;padding:20px;}
  .container{background:#f4f4f4;padding:20px;border-radius:10px;box-sizing:border-box;}
  h2{text-align:center;}
  label{font-weight:bold;}
  input[type="text"], input[type="number"], input[type="file"], select{width:100%;padding:10px;margin:8px 0;border:1px solid #ccc;border-radius:5px;box-sizing:border-box;}
  input[type="submit"], button{width:100%;padding:10px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;box-sizing:border-box;}
</style>
</head>
<body>
<div class="container">
<h2>Konfiguration</h2>
<form action="/save" method="post">
  <label for="wifi_ssid">WLAN-SSID:</label>
  <input type="text" id="wifi_ssid" name="wifi_ssid" value="%WIFI_SSID%">
  <label for="wifi_password">WLAN-Passwort:</label>
  <input type="text" id="wifi_password" name="wifi_password" value="%WIFI_PASSWORD%">
  <hr>
  <label for="deviceName">Gerätename:</label>
  <input type="text" id="deviceName" name="deviceName" value="%DEVICENAME%" required>
  <small>(%FULL_DEVICENAME%)</small>
  <br><br>
  <label for="idTag">Default Benutzer:</label>
  <input type="text" id="idTag" name="idTag" value="%IDTAG%" required>

  <h2>Fahrrad-Einstellungen</h2>
  <label for="wheel_size_preset">Radgröße (Standard):</label>
  <select id="wheel_size_preset" onchange="updateWheelSizeFromPreset()">
    <option value="">-- Manuelle Eingabe --</option>
    <option value="1590" %PRESET_20_SELECTED%>20 Zoll (1590 mm)</option>
    <option value="1910" %PRESET_24_SELECTED%>24 Zoll (1910 mm)</option>
    <option value="2075" %PRESET_26_SELECTED%>26 Zoll (2075 mm)</option>
    <option value="2224" %PRESET_28_SELECTED%>28 Zoll (2224 mm)</option>
    <option value="2300" %PRESET_29_SELECTED%>29 Zoll (2300 mm)</option>
  </select>
  <br><br>
  <label for="wheel_size">Radumfang (mm):</label>
  <input type="number" id="wheel_size" name="wheel_size" step="1" min="500" max="3000" value="%WHEELSIZE%" required oninput="updatePresetFromManual()">
  <small>Radumfang in Millimeter (500-3000 mm). Wählen Sie eine Standard-Radgröße oder geben Sie einen manuellen Wert ein.</small>
  <br><br>
  
  <script>
  function updateWheelSizeFromPreset() {
    var preset = document.getElementById('wheel_size_preset');
    var manual = document.getElementById('wheel_size');
    if (preset.value) {
      manual.value = preset.value;
    }
  }
  
  function updatePresetFromManual() {
    var preset = document.getElementById('wheel_size_preset');
    var manual = document.getElementById('wheel_size');
    var manualValue = parseInt(manual.value);
    
    // Check if manual value matches a preset (with 5mm tolerance)
    var presets = [
      {value: '1590', mm: 1590},
      {value: '1910', mm: 1910},
      {value: '2075', mm: 2075},
      {value: '2224', mm: 2224},
      {value: '2300', mm: 2300}
    ];
    
    var matched = false;
    for (var i = 0; i < presets.length; i++) {
      if (Math.abs(manualValue - presets[i].mm) <= 5) {
        preset.value = presets[i].value;
        matched = true;
        break;
      }
    }
    
    if (!matched) {
      preset.value = '';
    }
  }
  
  // Initialize preset selection on page load
  window.onload = function() {
    updatePresetFromManual();
  };
  </script>

  <label for="serverUrl">Webserver-URL:</label>
  <input type="text" id="serverUrl" name="serverUrl" value="%SERVERURL%">
  <br><br>
  <label for="apiKey">API Key:</label>
  <input type="text" id="apiKey" name="apiKey" value="%APIKEY%">
  <label for="sendInterval">Sendezyklus (Sekunden):</label>
  <input type="number" id="sendInterval" name="sendInterval" value="%SENDINTERVAL%" required>

  <hr>
  <h2>Config-WLAN-Einstellungen</h2>
  <label for="ap_password">Config-WLAN-Passwort (min. 8 Zeichen):</label>
  <input type="text" id="ap_password" name="ap_password" value="%AP_PASSWORD%" minlength="8" maxlength="64" required>
  <small>Passwort für den Config-WLAN-Hotspot. Änderung erfordert Neustart.</small>

  <h2>Geräte-Optionen</h2>
  <label for="ledEnabled">LED bei Puls</label>
  <input type="checkbox" id="ledEnabled" name="ledEnabled" value="1" %LEDCHECKED%>

  <br>
  <label for="debugEnabled">Debug-Modus</label>
  <input type="checkbox" id="debugEnabled" name="debugEnabled" value="1" %DEBUG_ENABLED%>
  
  <br><br>
  <label for="deepSleepTimeout">Deep-Sleep-Zeit:</label>
  <input type="number" id="deepSleepTimeout" name="deepSleepTimeout" value="%DEEPSLEEPTIMEOUT%" min="0" required>
  <small>Zeit in Sekunden ohne Impulse bis zum Deep-Sleep (0 = Deep-Sleep deaktiviert)</small>
  
  %TESTMODE_SECTION%
  <input type="submit" id="saveButton" value="Speichern" style="display:none;">
</form>
<hr>
<button onclick="document.getElementById('saveButton').click();" style="width:100%;padding:10px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;margin-bottom:10px;">Speichern</button>
<form action="/reboot" method="post">
  <input type="submit" value="Neustart" style="width:100%;padding:10px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;">
</form>
<hr>
<h2>Firmware-Update (OTA)</h2>
<form method="POST" action="/update" enctype="multipart/form-data">
  <input type="file" name="firmware">
  <input type="submit" value="Update">
</form>
</div>
</body>
</html>
)rawliteral";




// --- Web server functions ---
/**
 * @brief Handles HTTP GET request to root path ("/").
 * 
 * Serves the HTML configuration form with current values from NVS storage.
 * Replaces placeholders in HTML template with actual configuration values.
 * 
 * @note Pure logic function - web server response only
 * @note Side effects: Sends HTML response via WebServer, writes to Serial
 */
void handleRoot() {
  String html = HTML_FORM;
  html.replace("%WIFI_SSID%", preferences.getString("wifi_ssid", wifi_ssid));
  html.replace("%WIFI_PASSWORD%", preferences.getString("wifi_password", wifi_password));
  html.replace("%AP_PASSWORD%", getAPPassword());
  
  // Load device name and create full name with suffix
  String currentDeviceName = preferences.getString("deviceName", deviceName);
  html.replace("%DEVICENAME%", currentDeviceName);
  html.replace("%FULL_DEVICENAME%", currentDeviceName + "_" + deviceIdSuffix);
  
  html.replace("%IDTAG%", preferences.getString("idTag", idTag));
  
  float currentWheelSize = preferences.getFloat("wheel_size", wheel_size);
  Serial.print("Loaded wheel circumference for display: ");
  Serial.println(currentWheelSize, 1);
  
  // Display current wheel size in mm
  html.replace("%WHEELSIZE%", String(currentWheelSize, 1));
  
  // Determine which preset is selected (with 5mm tolerance)
  int currentSizeInt = (int)(currentWheelSize + 0.5); // Round to nearest integer
  String preset20Selected = "";
  String preset24Selected = "";
  String preset26Selected = "";
  String preset28Selected = "";
  String preset29Selected = "";
  
  if (abs(currentSizeInt - 1590) <= 5) {
    preset20Selected = "selected";
  } else if (abs(currentSizeInt - 1910) <= 5) {
    preset24Selected = "selected";
  } else if (abs(currentSizeInt - 2075) <= 5) {
    preset26Selected = "selected";
  } else if (abs(currentSizeInt - 2224) <= 5) {
    preset28Selected = "selected";
  } else if (abs(currentSizeInt - 2300) <= 5) {
    preset29Selected = "selected";
  }
  
  // Replace preset selection placeholders in HTML
  html.replace("%PRESET_20_SELECTED%", preset20Selected);
  html.replace("%PRESET_24_SELECTED%", preset24Selected);
  html.replace("%PRESET_26_SELECTED%", preset26Selected);
  html.replace("%PRESET_28_SELECTED%", preset28Selected);
  html.replace("%PRESET_29_SELECTED%", preset29Selected);
  
  html.replace("%LEDCHECKED%", preferences.getBool("ledEnabled", true) ? "checked" : "");
  html.replace("%DEBUG_ENABLED%", preferences.getBool("debugEnabled", false) ? "checked" : "");

  // Testmodus nur anzeigen, wenn vom Server aktiviert (NVS-Parameter "test_mode_admin_enabled")
  String testModeSection = "";
  if (preferences.getBool("test_mode_admin_enabled", false)) {
    testModeSection = "<hr>\n  <h2>Testmodus</h2>\n  <label for=\"testModeEnabled\">Testmodus</label>\n  <input type=\"checkbox\" id=\"testModeEnabled\" name=\"testModeEnabled\" value=\"1\" %TESTMODECHECKED%>\n  <br><br>\n  <label for=\"testDistance\">Simulierte Distanz (km):</label>\n  <input type=\"number\" id=\"testDistance\" name=\"testDistance\" step=\"0.01\" value=\"%TESTDISTANCE%\" required>\n  <label for=\"testInterval\">Sendeintervall (Sekunden):</label>\n  <input type=\"number\" id=\"testInterval\" name=\"testInterval\" value=\"%TESTINTERVAL%\" required>\n";
    testModeSection.replace("%TESTDISTANCE%", String(preferences.getFloat("testDistance", testDistance)));
    testModeSection.replace("%TESTINTERVAL%", String(preferences.getUInt("testInterval", testInterval_sec)));
    testModeSection.replace("%TESTMODECHECKED%", preferences.getBool("testModeEnabled", false) ? "checked" : "");
  }
  html.replace("%TESTMODE_SECTION%", testModeSection);
  
  html.replace("%SERVERURL%", preferences.getString("serverUrl", serverUrl));
  html.replace("%APIKEY%", preferences.getString("apiKey", apiKey));
  html.replace("%SENDINTERVAL%", String(preferences.getUInt("sendInterval", sendInterval_sec)));
  
  // Load deep sleep timeout from NVS
  unsigned long currentDeepSleep = preferences.getUInt("deep_sleep", 300);
  html.replace("%DEEPSLEEPTIMEOUT%", String(currentDeepSleep));
  
  server.send(200, "text/html", html);
}

/**
 * @brief Handles HTTP POST request to "/save" endpoint.
 * 
 * Processes form submission from configuration web interface. Saves all provided
 * configuration values to NVS storage and updates global variables. Validates and
 * normalizes server URL (adds http:// prefix if missing, removes trailing slashes).
 * 
 * @note Pure logic function - NVS storage operations only
 * @note Side effects: Writes to NVS storage, modifies global configuration variables, sends HTTP redirect
 */
void handleSave() {
  if (server.hasArg("wifi_ssid")) {
    preferences.putString("wifi_ssid", server.arg("wifi_ssid"));
    wifi_ssid = server.arg("wifi_ssid");
  }
  if (server.hasArg("wifi_password")) {
    preferences.putString("wifi_password", server.arg("wifi_password"));
    wifi_password = server.arg("wifi_password");
  }
  if (server.hasArg("deviceName")) {
    preferences.putString("deviceName", server.arg("deviceName"));
    deviceName = server.arg("deviceName");
  }
  if (server.hasArg("idTag")) {
    // Save as default_id_tag (not idTag) to distinguish from temporary RFID tag
    String newDefaultTag = server.arg("idTag");
    preferences.putString("default_id_tag", newDefaultTag);
    // Also update legacy "idTag" key for backward compatibility
    preferences.putString("idTag", newDefaultTag);
    idTag = newDefaultTag; // Update global variable
  }
  
  // Accept wheel circumference in millimeters (500-3000 mm)
  if (server.hasArg("wheel_size") && server.arg("wheel_size").length() > 0) {
      float newSizeMm = server.arg("wheel_size").toFloat();
      // Validate range: 500-3000 mm
      if (newSizeMm >= 500.0 && newSizeMm <= 3000.0) {
          preferences.putFloat("wheel_size", newSizeMm);
          wheel_size = newSizeMm;
          if (debugEnabled) {
              Serial.printf("DEBUG: Wheel size updated to: %.1f mm\n", newSizeMm);
          }
      } else {
          Serial.printf("WARNING: Wheel size out of valid range (%.1f mm, expected 500-3000 mm), keeping current value\n", newSizeMm);
      }
  }

  if (server.hasArg("serverUrl")) {
    String url = server.arg("serverUrl");
    url.trim(); // Remove leading/trailing whitespace

    // If URL is empty, clear it from NVS (will use default from build flag)
    if (url.length() == 0) {
        preferences.remove("serverUrl");
        serverUrl = "";
        // Default will be applied in getPreferences() if DEFAULT_SERVER_URL is defined
    } else {
        // Remove any trailing slashes to save only the base URL.
        while (url.endsWith("/")) {
            url.remove(url.length() - 1);
        }
        // Only add http:// prefix if URL doesn't already have a protocol
        // AND if the URL is not empty after trimming
        if (url.length() > 0 && !url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://" + url;
        }
        // Only save if URL is valid (not empty and has content after processing)
        if (url.length() > 0) {
            preferences.putString("serverUrl", url);
            serverUrl = url;
        } else {
            preferences.remove("serverUrl");
            serverUrl = "";
        }
    }
  }

  if (server.hasArg("apiKey")) {
    String key = server.arg("apiKey");
    key.trim(); // Remove leading/trailing whitespace
    
    // If key is empty, clear it from NVS (will use default from build flag)
    if (key.length() == 0) {
        preferences.remove("apiKey");
        apiKey = "";
        // Default will be applied in getPreferences() if DEFAULT_API_KEY is defined
    } else {
        preferences.putString("apiKey", key);
        apiKey = key;
    }
  }
  
  if (server.hasArg("ap_password")) {
    String newAPPassword = server.arg("ap_password");
    newAPPassword.trim();
    
    // Validate: minimum 8 characters (WPA2 requirement), empty not allowed
    if (newAPPassword.length() >= 8) {
        preferences.putString("ap_passwd", newAPPassword);
        Serial.println("Config AP password updated (restart required)");
        if (debugEnabled) {
            Serial.printf("DEBUG: New AP password saved: %s\n", newAPPassword.c_str());
        }
    } else if (newAPPassword.length() > 0) {
        Serial.println("WARNING: AP password too short (min 8 chars), keeping current password");
        if (debugEnabled) {
            Serial.printf("DEBUG: Rejected AP password (too short): %s\n", newAPPassword.c_str());
        }
    }
    // If empty, do nothing (empty password not allowed)
  }
  if (server.hasArg("sendInterval")) {
    preferences.putUInt("sendInterval", server.arg("sendInterval").toInt());
    sendInterval_sec = server.arg("sendInterval").toInt();
  }
  
  if (server.hasArg("deepSleepTimeout")) {
    unsigned long newDeepSleep = server.arg("deepSleepTimeout").toInt();
    // NVS key max length is 15 characters, so use shorter key
    preferences.putUInt("deep_sleep", newDeepSleep);
    deepSleepTimeout_sec = newDeepSleep;
    // If deepSleepTimeout_sec is 0, disable deep sleep immediately
    if (newDeepSleep == 0) {
        DeepSleep = false;
        Serial.println("Deep-Sleep deaktiviert (Zeit = 0)");
    } else {
        DeepSleep = true;
        Serial.printf("Deep-Sleep-Zeit aktualisiert: %lu Sekunden\n", newDeepSleep);
    }
  }
  
  ledEnabled = server.hasArg("ledEnabled");
  preferences.putBool("ledEnabled", ledEnabled);

  debugEnabled = server.hasArg("debugEnabled");
  preferences.putBool("debugEnabled", debugEnabled);

  testModeActive = server.hasArg("testModeEnabled");
  preferences.putBool("testModeEnabled", testModeActive);

  // Always save test data, regardless of test mode status
  if (server.hasArg("testDistance") && server.arg("testDistance").length() > 0) {
      preferences.putFloat("testDistance", server.arg("testDistance").toFloat());
  }
  if (server.hasArg("testInterval") && server.arg("testInterval").length() > 0) {
      preferences.putUInt("testInterval", server.arg("testInterval").toInt());
  }


  // NEW: Debug output of saved data
  if (debugEnabled) {
    Serial.println("\n--- NVS configuration saved ---");
    Serial.printf("WiFi SSID: %s\n", wifi_ssid.c_str());
    Serial.printf("WiFi password: %s\n", wifi_password.c_str());
    Serial.printf("Device name: %s\n", deviceName.c_str());
    Serial.printf("ID Tag: %s\n", idTag.c_str());
    Serial.printf("Wheel circumference: %.2f cm\n", wheel_size);
    Serial.printf("Server URL: %s\n", serverUrl.c_str());
    Serial.printf("API Key: %s\n", apiKey.c_str());
    Serial.printf("Send interval: %d s\n", sendInterval_sec);
    Serial.printf("LED enabled: %s\n", ledEnabled ? "Yes" : "No");
    Serial.printf("Debug mode: %s\n", debugEnabled ? "Yes" : "No");
    Serial.printf("Test mode: %s\n", testModeActive ? "Yes" : "No");
    Serial.printf("  Test distance: %.2f km\n", preferences.getFloat("testDistance", 0.0));
    Serial.printf("  Test interval: %u s\n", preferences.getUInt("testInterval", 0));
    Serial.println("-------------------------------------\n");
  }


  server.sendHeader("Location", String("/"));
  server.send(302, "text/plain", "OK");
}

/**
 * @brief Handles HTTP POST request to "/reboot" endpoint.
 * 
 * Triggers a device restart after sending confirmation response.
 * Used to apply configuration changes that require a restart.
 * 
 * @note Hardware interaction: ESP32 restart via ESP.restart()
 * @note Side effects: Restarts the entire device
 */
void handleReboot() {
  server.send(200, "text/plain", "Das Gerät wird neu gestartet...");
  delay(100);
  ESP.restart();
}

/**
 * @brief Handles HTTP POST request to "/update" endpoint for OTA firmware updates.
 * 
 * Processes multipart form data containing firmware binary. Handles upload in chunks
 * and writes to ESP32 flash memory using Update library. Supports OTA (Over-The-Air)
 * firmware updates without physical access to the device.
 * 
 * @note Hardware interaction: ESP32 flash memory (firmware update)
 * @note Side effects: Writes firmware to flash, may trigger device restart on success
 */
void handleUpdate() {
  HTTPUpload& upload = server.upload();
  
  if (upload.status == UPLOAD_FILE_START) {
    Serial.printf("Update start: %s\n", upload.filename.c_str());
    #ifdef ENABLE_OLED
    display_FirmwareUpdate();
    #endif
    if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
      Update.printError(Serial);
      server.send(500, "text/plain", "Update failed to start");
      return;
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
      server.send(500, "text/plain", "Update write failed");
      return;
    }
    // Progress feedback
    if (upload.totalSize > 0) {
      Serial.printf("Progress: %d%%\n", (upload.currentSize * 100) / upload.totalSize);
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.end(true)) {
      Serial.printf("Update successful: %u bytes\n", upload.totalSize);
      
      // Firmware version is now always read from build flag (FIRMWARE_VERSION)
      // No NVS cleanup needed - version is embedded in the binary
      if (debugEnabled) {
        Serial.println("DEBUG: Manual firmware upload completed.");
        Serial.println("DEBUG: Version will be read from FIRMWARE_VERSION build flag on next boot.");
      }
      
      // Send success response before restart
      server.sendHeader("Connection", "close");
      server.send(200, "text/plain", "Update erfolgreich! Gerät startet neu...");
      
      // Small delay to ensure response is sent
      delay(500);
      ESP.restart();
    } else {
      Update.printError(Serial);
      server.send(500, "text/plain", "Update failed");
    }
  } else if (upload.status == UPLOAD_FILE_ABORTED) {
    Update.abort();
    Serial.println("Update aborted");
    server.send(500, "text/plain", "Update aborted");
  }
}

/**
 * @brief Initializes and starts the configuration web server.
 * 
 * Creates a WiFi access point (AP) with dynamic SSID based on device MAC address,
 * starts the HTTP server, and registers all route handlers. The AP allows configuration
 * of the device via web browser when it cannot connect to a WiFi network.
 * 
 * @note Hardware interaction: WiFi radio (AP mode), OLED display (if enabled)
 * @note Side effects: Creates WiFi AP, starts HTTP server, updates OLED display, writes to Serial
 */
void setupConfigServer() {
    // Put ESP32 into dual mode (AP + Station)
    WiFi.mode(WIFI_AP_STA);
    
    // Dynamically create SSID with suffix
    String ap_ssid_dynamic = "MCC" + deviceIdSuffix;

    // Create Wi-Fi access point (AP) to host web server
    Serial.print("Creating access point with SSID: "); 
    Serial.println(ap_ssid_dynamic);
    String ap_password_dynamic = getAPPassword();
    if (debugEnabled) {
        Serial.printf("DEBUG: Starting AP with password: %s\n", ap_password_dynamic.c_str());
    }
    WiFi.softAP(ap_ssid_dynamic.c_str(), ap_password_dynamic.c_str());
    Serial.print("Access point created! IP address: "); 
    Serial.println(WiFi.softAPIP());

    extern const unsigned long CONFIG_TIMEOUT_SEC; // NEW: Externally declare timeout variable
    Serial.printf("Config mode active. Automatically ends after %u seconds without interaction.\n", CONFIG_TIMEOUT_SEC); // NEW: Timeout output

    // Define web server routes
    server.on("/", handleRoot);
    server.on("/save", handleSave);
    server.on("/reboot", handleReboot);
    // For multipart/form-data uploads, don't send response in POST handler
    // Response will be sent in handleUpdate() after upload completes
    server.on("/update", HTTP_POST, [](){
      // Do nothing here - handleUpdate() will process the upload
    }, handleUpdate);
    server.begin();
    Serial.println("HTTP server started");
}