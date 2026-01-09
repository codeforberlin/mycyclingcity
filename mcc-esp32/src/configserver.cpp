#include "configserver.h"
#include <WiFi.h>
#include <Update.h>

// --- Configuration ---
// SSID and password for configuration access point
const char* ap_password = "mccmuims";

// Wheel sizes in inches and calculated circumference in cm
struct WheelSize {
    int inches;
    float circumference_cm;
};

// Calculated wheel circumference (circumference = diameter * Pi).
// 20 inches: 50.8 cm -> circumference ~ 159.6 cm
// 24 inches: 60.96 cm -> circumference ~ 191.6 cm
// 26 inches: 66.04 cm -> circumference ~ 207.5 cm
// 28 inches: 71.12 cm -> circumference ~ 223.2 cm
WheelSize wheel_sizes[] = {
    {20, 159.6},
    {24, 191.6},
    {26, 207.5},
    {28, 223.2}
};

// HTML configuration form
const char* HTML_FORM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<title>ESP32 Bike Tacho Konfiguration</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta charset="UTF-8"> <style>
  body{font-family:Arial,sans-serif;margin:auto;max-width:600px;padding:20px;}
  .container{background:#f4f4f4;padding:20px;border-radius:10px;}
  h2{text-align:center;}
  label{font-weight:bold;}
  input[type="text"], input[type="number"], input[type="file"], select{width:100%;padding:10px;margin:8px 0;border:1px solid #ccc;border-radius:5px;}
  input[type="submit"]{width:100%;padding:10px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;}
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
  <label for="deviceName">Gerätename (device_id):</label>
  <input type="text" id="deviceName" name="deviceName" value="%DEVICENAME%" required>
  <small>(%FULL_DEVICENAME%)</small>
  <br><br>
  <label for="idTag">ID Tag (id_tag):</label>
  <input type="text" id="idTag" name="idTag" value="%IDTAG%" required>

  <h2>Fahrrad-Einstellungen</h2>
  <label for="wheelSizeDropdown">Radgröße:</label>
  <select name='wheelSizeDropdown' id='wheelSizeDropdown'>
    %WHEELSIZES_OPTIONS%
  </select>

  <label for="wheel_size">Manuelle Eingabe (cm):</label>
  <input type="number" id="wheel_size" name="wheel_size" step="0.1" value="%WHEELSIZE%">

  <label for="serverUrl">Webserver-URL (mit http:// oder https://):</label>
  <input type="text" id="serverUrl" name="serverUrl" value="%SERVERURL%">
  <label for="authToken">Base64 Auth Token:</label>
  <input type="text" id="authToken" name="authToken" value="%AUTHTOKEN%">
  <label for="sendInterval">Sendeintervall (Sekunden):</label>
  <input type="number" id="sendInterval" name="sendInterval" value="%SENDINTERVAL%" required>

  <h2>Geräte-Optionen</h2>
  <label for="ledEnabled">LED bei Puls</label>
  <input type="checkbox" id="ledEnabled" name="ledEnabled" value="1" %LEDCHECKED%>

  <br>
  <label for="debugEnabled">Debug-Modus</label>
  <input type="checkbox" id="debugEnabled" name="debugEnabled" value="1" %DEBUG_ENABLED%>
  
  <hr>
  <h2>Testmodus</h2>
  <label for="testModeEnabled">Testmodus</label>
  <input type="checkbox" id="testModeEnabled" name="testModeEnabled" value="1" %TESTMODECHECKED%>
  <br><br>
  <label for="testDistance">Simulierte Distanz (km):</label>
  <input type="number" id="testDistance" name="testDistance" step="0.01" value="%TESTDISTANCE%" required>
  <label for="testInterval">Sendeintervall (Sekunden):</label>
  <input type="number" id="testInterval" name="testInterval" value="%TESTINTERVAL%" required>
  <input type="submit" value="Speichern">
</form>
<hr>
<h2>Aktionen</h2>
<form action="/reboot" method="post">
  <input type="submit" value="Neustart">
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
  
  // Load device name and create full name with suffix
  String currentDeviceName = preferences.getString("deviceName", deviceName);
  html.replace("%DEVICENAME%", currentDeviceName);
  html.replace("%FULL_DEVICENAME%", currentDeviceName + "_" + deviceIdSuffix);
  
  html.replace("%IDTAG%", preferences.getString("idTag", idTag));
  
  float currentWheelSize = preferences.getFloat("wheel_size", wheel_size);
  Serial.print("Loaded wheel circumference for display: ");
  Serial.println(currentWheelSize, 1);
  
  String wheelSizeOptions = "";
  bool matchFound = false;

  // Wheel sizes in inches and calculated circumference in cm
  struct WheelSize {
      int inches;
      float circumference_cm;
  };

  WheelSize wheel_sizes[] = {
      {20, 159.6},
      {24, 191.6},
      {26, 207.5},
      {28, 223.2}
  };

  for (const auto& size : wheel_sizes) {
      String selected = "";
      if (abs(currentWheelSize - size.circumference_cm) < 0.1) {
          selected = "selected";
          matchFound = true;
          Serial.printf("Match found! %s inches selected.\n", String(size.inches).c_str());
      }
      wheelSizeOptions += "<option value='" + String(size.circumference_cm) + "' " + selected + ">" + String(size.inches) + " Zoll (" + String(size.circumference_cm, 1) + " cm)</option>";
  }

  String manualValue = "";
  if (!matchFound) {
      wheelSizeOptions += "<option value='manual' selected>Manuelle Auswahl</option>";
      manualValue = String(currentWheelSize);
      Serial.println("Saved value is a manual entry. Menu item 'Manual selection' will be selected.");
  } else {
      wheelSizeOptions += "<option value='manual'>Manuelle Auswahl</option>";
  }

  html.replace("%WHEELSIZES_OPTIONS%", wheelSizeOptions);
  html.replace("%WHEELSIZE%", manualValue);
  
  html.replace("%LEDCHECKED%", preferences.getBool("ledEnabled", true) ? "checked" : "");
  html.replace("%DEBUG_ENABLED%", preferences.getBool("debugEnabled", false) ? "checked" : "");

  html.replace("%TESTDISTANCE%", String(preferences.getFloat("testDistance", testDistance)));
  html.replace("%TESTINTERVAL%", String(preferences.getUInt("testInterval", testInterval_sec)));
  html.replace("%TESTMODECHECKED%", preferences.getBool("testModeEnabled", false) ? "checked" : "");
  
  html.replace("%SERVERURL%", preferences.getString("serverUrl", serverUrl));
  html.replace("%AUTHTOKEN%", preferences.getString("authToken", authToken));
  html.replace("%SENDINTERVAL%", String(preferences.getUInt("sendInterval", sendInterval_sec)));
  
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
    preferences.putString("idTag", server.arg("idTag"));
    idTag = server.arg("idTag");
  }
  
  // Correctly accept wheel circumference: manual entry takes priority
  if (server.hasArg("wheelSizeDropdown") && server.arg("wheelSizeDropdown") == "manual") {
      if (server.hasArg("wheel_size") && server.arg("wheel_size").length() > 0) {
          float customSize = server.arg("wheel_size").toFloat();
          preferences.putFloat("wheel_size", customSize);
          wheel_size = customSize;
      }
  } else if (server.hasArg("wheelSizeDropdown")) {
      float dropdownSize = server.arg("wheelSizeDropdown").toFloat();
      preferences.putFloat("wheel_size", dropdownSize);
      wheel_size = dropdownSize;
  }

  if (server.hasArg("serverUrl")) {
    String url = server.arg("serverUrl");

    // Remove any trailing slashes to save only the base URL.
    while (url.endsWith("/")) {
        url.remove(url.length() - 1);
    }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
        url = "http://" + url;
    }
    preferences.putString("serverUrl", url);
    serverUrl = url;
  }

  if (server.hasArg("authToken")) {
    preferences.putString("authToken", server.arg("authToken"));
    authToken = server.arg("authToken");
  }
  if (server.hasArg("sendInterval")) {
    preferences.putUInt("sendInterval", server.arg("sendInterval").toInt());
    sendInterval_sec = server.arg("sendInterval").toInt();
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
    Serial.printf("Auth Token: %s\n", authToken.c_str());
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
  server.sendHeader("Connection", "close");
  server.send(200, "text/plain", "Update gestartet...");

  HTTPUpload& upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.end(true)) {
      Serial.printf("Update successful. Restarting...\n");
    } else {
      Update.printError(Serial);
    }
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
    WiFi.softAP(ap_ssid_dynamic.c_str(), ap_password);
    Serial.print("Access point created! IP address: "); 
    Serial.println(WiFi.softAPIP());

    extern const unsigned long CONFIG_TIMEOUT_SEC; // NEW: Externally declare timeout variable
    Serial.printf("Config mode active. Automatically ends after %u seconds without interaction.\n", CONFIG_TIMEOUT_SEC); // NEW: Timeout output

    // Define web server routes
    server.on("/", handleRoot);
    server.on("/save", handleSave);
    server.on("/reboot", handleReboot);
    server.on("/update", HTTP_POST, [](){
      server.sendHeader("Connection", "close");
      server.send(200, "text/plain", "Update gestartet...");
    }, handleUpdate);
    server.begin();
    Serial.println("HTTP server started");
}