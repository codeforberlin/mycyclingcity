#ifndef CONFIGSERVER_H
#define CONFIGSERVER_H

#include <Arduino.h>
#include <WebServer.h>
#include <Preferences.h>

// Globale Variablen, die in main.cpp definiert sind
extern WebServer server;
extern Preferences preferences;
extern bool configMode;
extern bool testActive;
extern bool debugEnabled;

extern String wifi_ssid;
extern String wifi_password;
extern String deviceName;
extern String idTag;
extern float wheel_size;
extern String serverUrl;
extern String authToken;
extern unsigned int sendInterval_sec;
extern bool ledEnabled;
extern float testDistance;
extern unsigned int testInterval_sec;
extern bool debugEnabled; 
extern bool testModeActive;
extern String deviceIdSuffix;

extern const unsigned long CONFIG_TIMEOUT_SEC; // NEU: Timeout-Konstante

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
void setupConfigServer();

#endif