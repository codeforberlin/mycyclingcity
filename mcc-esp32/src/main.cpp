/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    main.cpp
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Update.h>
#include "driver/pcnt.h"
#include "configserver.h"
#include "esp_system.h" // unique chip ID
#include "led_control.h" // Header for LED control
#include "device_management.h" // Device management APIs
// getFirmwareVersion() is declared in device_management.h

#ifdef ENABLE_OLED
#include <U8g2lib.h>  // OLED display library if an OLED display is used
#endif

#ifdef ENABLE_OLED
#include <Wire.h>
#endif

#ifdef ENABLE_RFID
#include <SPI.h>
#include <MFRC522.h>
#include "rfid_mfrc522_control.h"
#endif 


// --- GLOBAL HARDWARE DEFINITIONS ---

#ifdef ENABLE_OLED
// PINS FOR OLED I2C: SDA=21, SCL=22
// IMPORTANT: Pin values now come from build flag, we use flag names here
#ifndef OLED_RST_PIN
  #define OLED_RST_PIN   -1 // Fallback if flag is missing
#endif
#ifndef OLED_SDA_PIN
  #define OLED_SDA_PIN   17 // Fallback if flag is missing
#endif
#ifndef OLED_SCL_PIN
  #define OLED_SCL_PIN   18 // Fallback if flag is missing
#endif

// OLED object (constructor uses build flag definitions)
// We need to rename the 'display' variable to avoid conflicts, or adjust the constructor. The current code uses:
// U8G2_SSD1306_128X64_NONAME_F_HW_I2C display(U8G2_R0, OLED_RST); // <-- must be adjusted.
// Correction: Constructor expects pin value directly.

// OLED object
// Use the new pin names defined by build flag:
// Use 4-parameter constructor to explicitly specify RST, SCL, SDA
// This works for both Heltec V3 (RST=21) and wemos_d1_mini32 (RST=-1)
// U8G2 handles -1 for RST correctly (no reset pin)
U8G2_SSD1306_128X64_NONAME_F_HW_I2C display(U8G2_R0, OLED_RST_PIN, OLED_SCL_PIN, OLED_SDA_PIN);
#endif

#ifdef ENABLE_RFID
// RFID module
// --- GLOBAL VARIABLES (DEFINITIONS) ---
#define RST_PIN         26
#define SS_PIN          5

// MFRC522 instance and interrupt variable
MFRC522 mfrc522(SS_PIN, RST_PIN);
#endif


// Checks if the build flag "PIO_BUILD_TEST_MODE" is set.
#ifdef PIO_BUILD_TEST_MODE
  #include "test_config.h"
#endif

// --- Configuration ---
// GPIO pin for counting
    // PulsePin with external 10 KOhm pull-up resistor to 3.3V for HIGH and 100nF capacitor between ground and 3.3V
    // Internal software pull-up doesn't work because it goes LOW shortly after DeepSleep and ESP32 wakes up immediately
    // The pin for checking pulses is individually set in .platformio.ini for each board
#ifdef PulseMeasurePin
  #define SENSOR_PIN PulseMeasurePin
#endif

// Configure PCNT unit
#define PCNT_UNIT PCNT_UNIT_0

// Wait time at the beginning of setup for configuration mode (in milliseconds)
//RR const unsigned long CONFIG_WAIT_TIME_MS = 120000; // 2 min= 120000

bool DeepSleep = true;
unsigned long deepSleepTimeout_sec = 300; // Time in seconds until deep sleep, default 300 seconds

// --- Global variables (definitions) ---
// API endpoint paths (legacy - device management APIs are in device_management.h)
const char* API_UPDATE_DATA_PATH = "/api/update-data"; // Path for sending tachometer data
const char* API_GET_USER_ID_PATH = "/api/get-user-id"; // Path for retrieving user data

// global variables for configuration mode
const unsigned long CONFIG_TIMEOUT_SEC = 300; // Timeout in seconds (5 minutes)
unsigned long configModeTimeout_sec = CONFIG_TIMEOUT_SEC;
unsigned long configModeStartTime = 0; // Start time for timeout
bool wasConfigExit = false;  // Temporary flag for restart reason
bool configModeForced = false; // Flag whether configuration mode was forced

WebServer server(80);
Preferences preferences;
bool configMode = false;
bool testActive = false;
bool debugEnabled = true;
bool testModeActive = false;

// Static variables for config mode RFID tag detection
// These track the idTag value when config mode started to detect NEW RFID tags
static String idTagAtConfigStart = "";
static bool idTagAtConfigStartInitialized = false;

String wifi_ssid = "";
String wifi_password = "";
String deviceName = "";
String idTag = "";        // uid from RFID tag
String username ="";      // internal symbolic name from admin database
String lastSentIdTag = "";
bool idTagFromRFID = false;  // Track if current idTag came from RFID detection (true) or default user (false)
unsigned long lastServerErrorTime = 0;  // Track last server error time for backoff
unsigned long serverErrorBackoffInterval = 60000;  // Wait 60 seconds between retries after server error
bool apiKeyErrorActive = false;  // Track if API key error is active (don't show username error until fixed)
int wifiConnectAttempts = 0;  // Track number of WiFi connection attempts (max 3)
float wheel_size = 2075.0;  // Default: 26 Zoll = 2075 mm circumference
String serverUrl = "";
String apiKey = "";
unsigned int sendInterval_sec = 30;
bool ledEnabled = true;
float testDistance = 1.0;
unsigned int testInterval_sec = 10;
bool ledIsOn = false;
unsigned long ledOnTime = 0;
float speed_kmh = 0;
unsigned int configFetchInterval_sec = 3600; // Default: 1 hour
unsigned long lastConfigFetchTime = 0; // Timestamp of last config fetch
// variables for OLED
int textWidth=0;
const char* textline="";

// Counter and distance
int16_t currentPulseCount = 0;
int16_t lastPulseCount = 0;
float totalDistance_mm = 0;       // total distance traveled for current user since start or wakeup (in mm)
float distanceInInterval_mm = 0; // distance traveled between two send cycles (in mm)
int16_t pulsesAtLastSend = 0; // stores counter value at last send

// Timer for data transmission
unsigned long lastDataSendTime = 0;
unsigned long reconnectLastAttemptTime = 0;
const unsigned long RECONNECT_INTERVAL_MS = 30000;

// Global variable for suffix
String deviceIdSuffix;


unsigned long lastPulseTime = 0; // Timestamp of last pulse
float currentSpeed_kmh = 0.0; // Current speed calculated from time between pulses (averaged)
unsigned long previousPulseTime = 0; // Timestamp of previous pulse for speed calculation
const unsigned long SPEED_TIMEOUT_MS = 5000; // After 5 seconds without pulse → 0 km/h
const int SPEED_AVERAGE_COUNT = 5; // Number of pulses to average for speed smoothing
float speedHistory[SPEED_AVERAGE_COUNT] = {0.0, 0.0, 0.0, 0.0, 0.0}; // Array to store last 5 speed values
int speedHistoryIndex = 0; // Current index in speed history array
int speedHistoryCount = 0; // Number of valid values in speed history (0 to SPEED_AVERAGE_COUNT)

// --- Function prototypes ---
/**
 * @brief Connects the ESP32 to a WiFi network using stored credentials.
 * 
 * Reads WiFi SSID and password from global variables and attempts connection.
 * Updates OLED display (if enabled) with connection status.
 * 
 * @note Hardware interaction: OLED display (if ENABLE_OLED is defined)
 * @note Side effects: Modifies WiFi state, updates OLED display, writes to Serial
 */
void connectToWiFi();

/**
 * @brief Sends tachometer data to the configured server via HTTP POST.
 * 
 * Sends distance, speed, and pulse data as JSON to the server API endpoint.
 * Handles both test mode (simulated data) and normal mode (real measurements).
 * 
 * @param currentSpeed_kmh Current speed in kilometers per hour
 * @param distanceInInterval_mm Distance traveled in the interval in millimeters
 * @param pulsesInInterval Number of pulses detected in the interval
 * @param isTest If true, sends simulated test data instead of real measurements
 * @return HTTP status code on success (>0), -1 on WiFi error, -2 on configuration error
 * 
 * @note Hardware interaction: LED_PIN (blinks during transmission)
 * @note Side effects: Sends HTTP request, controls LED, writes to Serial
 */
int  sendDataToServer(float currentSpeed_kmh, float distanceInInterval_mm, int pulsesInInterval, bool isTest);

/**
 * @brief Displays all configuration values stored in NVS to Serial output.
 * 
 * Prints WiFi settings, device configuration, wheel size, server URL, and test mode settings.
 * 
 * @note Pure logic function - no hardware interaction
 * @note Side effects: Writes to Serial output
 */
void displayNVSConfig();

/**
 * @brief Configures ESP32 deep sleep wakeup trigger.
 * 
 * Sets up the sensor pin (SENSOR_PIN) as wakeup source for deep sleep mode.
 * The device will wake up when the pin goes LOW.
 * 
 * @note Hardware interaction: SENSOR_PIN (GPIO configuration for wakeup)
 * @note Side effects: Configures ESP32 sleep wakeup source
 */
void setupDeepSleep();

/**
 * @brief Loads all configuration values from NVS (Non-Volatile Storage) into global variables.
 * 
 * Reads WiFi credentials, device settings, wheel size, server configuration, and test mode
 * settings from persistent storage. Falls back to build flags if NVS values are empty.
 * 
 * @note Pure logic function - reads from NVS storage
 * @note Side effects: Modifies global configuration variables, writes to Serial
 */
void getPreferences();

/**
 * @brief Resets all distance and pulse counters to zero.
 * 
 * Clears both software counters and hardware PCNT unit. Called when a new RFID tag is detected
 * to start fresh distance tracking for the new user.
 * 
 * @note Hardware interaction: PCNT_UNIT (hardware pulse counter)
 * @note Side effects: Resets global distance variables and hardware counter
 */
void resetDistanceCounters();

// Buzzer function prototypes
/**
 * @brief Generates a tone on the buzzer for a specified duration.
 * 
 * Controls the active buzzer by setting BUZZER_PIN HIGH for the duration, then LOW.
 * 
 * @param duration_ms Duration of the tone in milliseconds
 * 
 * @note Hardware interaction: BUZZER_PIN (GPIO output)
 * @note Side effects: Blocks execution for duration_ms milliseconds
 */
void buzzer_tone(int duration_ms);

/**
 * @brief Plays startup tone sequence (3 short beeps).
 * 
 * Indicates device restart after power-on. Plays 3 beeps of 100ms each with 100ms pauses.
 * 
 * @note Hardware interaction: BUZZER_PIN
 * @note Side effects: Blocks execution for ~500ms
 */
void play_startup_tone();

/**
 * @brief Plays wakeup tone sequence (2 short beeps).
 * 
 * Indicates wakeup from deep sleep. Plays 2 beeps of 150ms each with 150ms pause.
 * 
 * @note Hardware interaction: BUZZER_PIN
 * @note Side effects: Blocks execution for ~450ms
 */
void play_wakeup_tone();

/**
 * @brief Plays tag detected tone (1 long beep).
 * 
 * Indicates successful RFID tag detection. Plays 1 beep of 500ms.
 * 
 * @note Hardware interaction: BUZZER_PIN
 * @note Side effects: Blocks execution for 500ms
 */
void play_tag_detected_tone();

/**
 * @brief Displays ID tag name on OLED display.
 * 
 * Shows a message indicating that an ID tag was recognized (from RFID or NVS) and displays the associated
 * username or "NULL" if no assignment found. Works independently of RFID - displays any idTag.
 * 
 * @param text Username string to display (or "NULL" if not found)
 * 
 * @note Hardware interaction: OLED display (I2C communication)
 * @note Side effects: Updates OLED display buffer and sends to display
 * @note Only compiled if ENABLE_OLED is defined
 */
#ifdef ENABLE_OLED
void display_IdTag_Name(const char* text, bool isRfidDetected = false, bool queryWasSuccessful = false);
void display_ServerError(const char* errorType, int errorCode);
#endif

/**
 * @brief Queries the backend server to retrieve username for a given RFID tag ID.
 * 
 * Sends HTTP POST request to API_GET_USER_ID_PATH endpoint with the tag ID.
 * Parses JSON response to extract user_id field.
 * 
 * @param tagId Reference to String containing the RFID tag UID in hex format
 * @return String containing username if found, "NULL" if not found or on error, "FEHLER" on JSON parse error
 * 
 * @note Pure logic function - network communication only
 * @note Side effects: Sends HTTP request, writes to Serial
 */
String getUserIdFromTag(String& tagId);

/**
 * @brief Displays current cycling data on OLED display.
 * 
 * Shows username, current pulse count, and total distance traveled in kilometers.
 * 
 * @note Hardware interaction: OLED display (I2C communication)
 * @note Side effects: Updates OLED display buffer and sends to display
 * @note Only compiled if ENABLE_OLED is defined
 */
void display_Data();

// --- Setup ---
/**
 * @brief Main setup function called once at device startup.
 * 
 * Initializes all hardware components (LED, buzzer, OLED, RFID reader, PCNT counter),
 * loads configuration from NVS, checks for critical missing settings, and determines
 * whether to enter configuration mode or normal operation mode.
 * 
 * Configuration mode is entered if:
 * - Device was not woken from deep sleep (normal restart)
 * - Critical configuration is missing (WiFi, ID tag, wheel size, server URL, auth token)
 * 
 * @note Hardware interactions:
 *   - BUZZER_PIN: Initialized as OUTPUT, set LOW
 *   - LED_PIN: Initialized as OUTPUT, briefly flashed
 *   - VEXT_PIN: Set LOW to power OLED (Heltec boards only)
 *   - OLED display: Initialized via I2C (if ENABLE_OLED)
 *   - RFID MFRC522: Initialized via SPI
 *   - SENSOR_PIN: Configured for PCNT pulse counting
 *   - PCNT_UNIT: Configured for hardware pulse counting
 * 
 * @note Side effects: Initializes all hardware, loads NVS preferences, may start WiFi AP
 */
void setup() {
    Serial.begin(115200); 
    delay(1000);


    Serial.printf("Setup: debugEnabled= %d\n", debugEnabled);

    // Generate unique device ID
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    char macSuffix[5];
    sprintf(macSuffix, "%02X%02X", mac[4], mac[5]);
    deviceIdSuffix = String("_") + String(macSuffix);


    Serial.println("Setup: Reading configuration from NVS storage, getPreferences ...");
    delay(1000);
    preferences.begin("bike-tacho", false);
    getPreferences();
    
    // Initialize device management (loads timestamps, firmware version)
    initDeviceManagement();

    // ----------------------------------------------------------------------
    // CHECK and CLEAR CONFIG-EXIT FLAG
    // ----------------------------------------------------------------------
    bool wasConfigExit = preferences.getBool("configExit", false);
    if (wasConfigExit) {
        if (!preferences.putBool("configExit", false)) { // Reset flag immediately
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'configExit' to NVS\n");
        }
        Serial.println("INFO: Previous restart was triggered to exit configuration mode.");
    }

    // ----------------------------------------------------------------------
    // CHECK CRITICAL CONFIGURATIONS
    // ----------------------------------------------------------------------
    // Note: serverUrl and apiKey are not critical if DEFAULT values are available
    // This allows devices to connect to server without manual configuration
    // Final configuration can be done remotely via mcc-web admin interface
    bool serverUrlMissing = (serverUrl.length() == 0);
    bool apiKeyMissing = (apiKey.length() == 0);
    
    #ifdef DEFAULT_SERVER_URL
    bool serverUrlCritical = false; // Default available, not critical
    #else
    bool serverUrlCritical = serverUrlMissing; // No default, so missing is critical
    #endif
    
    #ifdef DEFAULT_API_KEY
    bool apiKeyCritical = false; // Default available, not critical
    #else
    bool apiKeyCritical = apiKeyMissing; // No default, so missing is critical
    #endif
    
    // Check for default_id_tag (not idTag, as idTag might be temporarily set by RFID)
    String defaultIdTagCheck = preferences.getString("default_id_tag", "");
    if (defaultIdTagCheck.length() == 0) {
        defaultIdTagCheck = preferences.getString("idTag", ""); // Fallback to legacy key
    }
    
    bool criticalConfigMissing = false;
    String missingParameter = "";  // Store the first missing parameter for OLED display
    
    // Check each critical parameter individually and report which one is missing
    if (wifi_ssid.length() == 0) {
        criticalConfigMissing = true;
        if (missingParameter.length() == 0) missingParameter = "wifi_ssid";
        Serial.println("ERROR: getPreferences() - Critical parameter 'wifi_ssid' is missing!");
    }
    // wifi_password.length() == 0 || // Password can be empty, e.g. for Freifunk
    if (defaultIdTagCheck.length() == 0) {
        criticalConfigMissing = true;
        if (missingParameter.length() == 0) missingParameter = "default_id_tag";
        Serial.println("ERROR: getPreferences() - Critical parameter 'default_id_tag' (or 'idTag') is missing!");
    }
    if (wheel_size < 500.0 || wheel_size > 3000.0) {  // Valid range: 500-3000 mm
        criticalConfigMissing = true;
        if (missingParameter.length() == 0) missingParameter = "wheel_size";
        Serial.printf("ERROR: getPreferences() - Critical parameter 'wheel_size' is invalid (value: %.1f mm, valid range: 500-3000 mm)!\n", wheel_size);
    }
    if (sendInterval_sec == 0) {
        criticalConfigMissing = true;
        if (missingParameter.length() == 0) missingParameter = "sendInterval";
        Serial.println("ERROR: getPreferences() - Critical parameter 'sendInterval' is missing or zero!");
    }
    if (serverUrlCritical) {
        criticalConfigMissing = true;
        if (missingParameter.length() == 0) missingParameter = "serverUrl";
        Serial.println("ERROR: getPreferences() - Critical parameter 'serverUrl' is missing!");
    }
    if (apiKeyCritical) {
        criticalConfigMissing = true;
        if (missingParameter.length() == 0) missingParameter = "apiKey";
        Serial.println("ERROR: getPreferences() - Critical parameter 'apiKey' is missing!");
    }

    if (criticalConfigMissing) {
        configMode = true;
        configModeForced = true;
        Serial.println("WARNING: Critical configurations missing! Forcing configuration mode.");
        
        // Display missing parameter on OLED
        #ifdef ENABLE_OLED
        display.clearBuffer();
        display.setFont(u8g2_font_7x14_tf);
        
        textline = "Fehler:";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 12);
        display.print(textline);
        
        // Format parameter name for display (replace underscores with spaces, capitalize)
        String paramDisplay = missingParameter;
        paramDisplay.replace("_", " ");
        // Capitalize first letter
        if (paramDisplay.length() > 0) {
            paramDisplay.setCharAt(0, toupper(paramDisplay.charAt(0)));
        }
        
        // Split long parameter names across two lines if needed
        String paramLine1 = "";
        String paramLine2 = "";
        
        if (missingParameter == "wifi_ssid") {
            paramLine1 = "WiFi SSID";
            paramLine2 = "fehlt";
        } else if (missingParameter == "default_id_tag") {
            paramLine1 = "ID-Tag";
            paramLine2 = "fehlt";
        } else if (missingParameter == "wheel_size") {
            paramLine1 = "Raddurchmesser";
            paramLine2 = "ungültig";
        } else if (missingParameter == "sendInterval") {
            paramLine1 = "Send-Intervall";
            paramLine2 = "fehlt";
        } else if (missingParameter == "serverUrl") {
            paramLine1 = "Server-URL";
            paramLine2 = "fehlt";
        } else if (missingParameter == "apiKey") {
            paramLine1 = "API-Key";
            paramLine2 = "fehlt";
        } else {
            // Fallback: use formatted parameter name
            paramLine1 = paramDisplay;
            paramLine2 = "fehlt";
        }
        
        textline = paramLine1.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 28);
        display.print(textline);
        
        if (paramLine2.length() > 0) {
            textline = paramLine2.c_str();
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 44);
            display.print(textline);
        }
        
        display.sendBuffer();
        #endif
    }
    
    // Initialize buzzer pin
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW); // Turn off buzzer initially
    
    // Initialize LED - let there be light!
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);  // ON - we're alive!
    delay(1000);
    digitalWrite(LED_PIN, LOW);  // OFF
    
    #ifdef ENABLE_OLED
    #ifdef BOARD_HELTEC
    // Turn on display - time to show
    Serial.println("DEBUG: Turning on display - time to show");
    pinMode(VEXT_PIN, OUTPUT);
    digitalWrite(VEXT_PIN, LOW);  // LOW = ON (intuitive!)
    delay(50);  // Give display time to power up (as in example code)
    #endif
    
    // Initialize display
    // Note: U8G2 with 4-parameter constructor handles I2C initialization internally
    display.begin();
    if (debugEnabled) {
        Serial.println("DEBUG: OLED display.begin() called");
    }
    #endif
 
    // RFID reader
    #ifdef ENABLE_RFID
    RFID_MFRC522_setup();
    #endif
    
    // Print sensor PIN configuration
    Serial.printf("SENSOR_PIN: %.d \n", SENSOR_PIN);

    // Check wakeup reason
    esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();

    // ----------------------------------------------------------------------
    // Logic for configuration mode - ALWAYS start on restart
    // ----------------------------------------------------------------------
    if (wakeup_reason != ESP_SLEEP_WAKEUP_EXT0 && !wasConfigExit) {
        
        configMode = true; // Always activate configuration mode on restart
        
        Serial.println("Starting configuration mode (Automatic on every restart).");
        configModeStartTime = millis(); // Start of timeout
        
        // Store current idTag value to detect if a new RFID tag is detected during config mode
        // This prevents false triggers from the idTag loaded from NVS
        // Note: This will be reset when config mode starts in loop()

        String ap_ssid_dynamic = "MCC" + deviceIdSuffix;

        #ifdef ENABLE_OLED
        // First show firmware version for 5 seconds on first start
        display.clearBuffer();
        display.setFont(u8g2_font_7x14_tf);

        textline = "MyCyclingCity";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 12); 
        display.print(textline);

        textline = deviceName.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 28); 
        display.print(textline);

        textline = "Firmware Version";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 44);
        display.print(textline);

        String fwVersion = "v" + getFirmwareVersion();
        textline = fwVersion.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 60);
        display.print(textline);

        display.sendBuffer();
        delay(5000);  // Show firmware version for 5 seconds

        // Now show config mode parameters
        display.clearBuffer();
        display.setFont(u8g2_font_7x14_tf);

        textline = "MyCyclingCity";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 12); 
        display.print(textline);

        textline = deviceName.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 28); 
        display.print(textline);
              
        display.drawStr(0, 44, "SSID: ");  
        display.drawStr(40, 44, ap_ssid_dynamic.c_str());

        display.drawStr(0, 60, "IP: ");  
        display.drawStr(40, 60, "192.168.4.1");
  
        display.sendBuffer();
        #endif
        
        play_startup_tone(); // <-- CALL: 3x short

        setupConfigServer();

        // Don't end setup here so code in loop() runs and checks timeout/pulse.
    } else {
        configMode = false;
        Serial.println("Awakened from deep sleep. Skipping configuration check.");
        play_wakeup_tone(); // <-- CALL: 2x short
        Serial.println("DEBUG: Setup - connectToWiFi() ...");
        connectToWiFi();
        
        // Send heartbeat and fetch config after wakeup from deep sleep
        if (WiFi.status() == WL_CONNECTED) {
            if (debugEnabled) {
                Serial.println("DEBUG: Sending heartbeat after wakeup from deep sleep...");
            }
            sendHeartbeat();
            
            // Fetch device configuration after wakeup from deep sleep
            if (configFetchInterval_sec > 0) {
                if (debugEnabled) {
                    Serial.println("DEBUG: Fetching device configuration after wakeup from deep sleep...");
                }
                if (fetchDeviceConfig()) {
                    lastConfigFetchTime = millis();
                    // Reload default_id_tag from NVS after config fetch, in case it was updated
                    // This ensures we use the default_id_tag, not any temporary RFID tag
                    String defaultIdTag = preferences.getString("default_id_tag", "");
                    if (defaultIdTag.length() == 0) {
                        defaultIdTag = preferences.getString("idTag", ""); // Fallback to legacy key
                    }
                    if (defaultIdTag.length() > 0) {
                        idTag = defaultIdTag; // Restore default_id_tag after config fetch
                        idTagFromRFID = false; // Default user, not from RFID
                        if (debugEnabled) {
                            Serial.printf("DEBUG: Default ID tag restored after config fetch: %s\n", defaultIdTag.c_str());
                        }
                    }
                    if (debugEnabled) {
                        Serial.println("DEBUG: Config fetched successfully after wakeup");
                    }
                } else {
                    if (debugEnabled) {
                        Serial.println("DEBUG: Config fetch failed after wakeup, will retry later");
                    }
                }
            }
        }

        // ... (OLED code for deep sleep wakeup remains) ...
    }
        
    // Configure PCNT unit
    Serial.println("Setup: Configuring ESP32 PCNT counter");
    pcnt_config_t pcnt_config = {};
    pcnt_config.pulse_gpio_num = SENSOR_PIN;
    pcnt_config.ctrl_gpio_num = PCNT_PIN_NOT_USED;
    pcnt_config.unit = PCNT_UNIT;
    pcnt_config.channel = PCNT_CHANNEL_0;
    pcnt_config.counter_h_lim = 0;
    pcnt_config.counter_l_lim = 0;
    pcnt_config.pos_mode = PCNT_COUNT_INC;
    pcnt_config.neg_mode = PCNT_COUNT_DIS;
    pcnt_config.lctrl_mode = PCNT_MODE_KEEP;
    pcnt_config.hctrl_mode = PCNT_MODE_KEEP;
    pcnt_unit_config(&pcnt_config);
    pcnt_counter_clear(PCNT_UNIT);
    // 1000 clock cycles / 80,000,000 clock cycles per second = 0.0000125 seconds or 12.5 microseconds
    pcnt_set_filter_value(PCNT_UNIT, 1023); // wait number of clock cycles, max 1023 cycles definable
    pcnt_filter_enable(PCNT_UNIT);
    // Start the PCNT counter so it can detect pulses
    pcnt_counter_resume(PCNT_UNIT);
    
    // Set initial send time
    lastDataSendTime = millis();

    // Initialize deep sleep
    //setupDeepSleep(); 

    Serial.println("Setup finished, starting loop ...");
    
}

// --- Loop ---
/**
 * @brief Main loop function called repeatedly after setup.
 * 
 * Handles two main modes:
 * 1. Configuration mode: Serves web configuration interface, handles timeout and pulse detection exit
 * 2. Normal mode: Monitors RFID tags, pulse counter, sends data to server, manages deep sleep
 * 
 * In normal mode, the loop:
 * - Processes RFID tag detection and updates user ID
 * - Monitors WiFi connection and attempts reconnection if needed
 * - Reads pulse counter and calculates distance/speed
 * - Sends data to server at configured intervals
 * - Manages deep sleep when no activity detected
 * 
 * @note Hardware interactions:
 *   - RFID MFRC522: Polled for new cards
 *   - PCNT_UNIT: Pulse count read periodically
 *   - LED_PIN: Blinked on pulse detection
 *   - SENSOR_PIN: Read for deep sleep trigger condition
 *   - OLED display: Updated with cycling data (if enabled)
 *   - VEXT_PIN: Controlled for OLED power management
 * 
 * @note Side effects: Continuous monitoring, periodic HTTP requests, hardware state changes
 */
void loop() {

    // --- CALL RFID PROCESSING ---
    #ifdef ENABLE_RFID
    RFID_MFRC522_loop_handler();
    #endif
        
    if (configMode) {
        server.handleClient();
        delay(1);

        // --- End configuration mode on RFID tag detection ---
        // Check if an RFID tag was detected (idTag was updated by RFID_MFRC522_loop_handler)
        // IMPORTANT: Only react if idTag was actually changed by RFID detection, not if it was loaded from NVS
        
        // Initialize idTagAtConfigStart on first entry to config mode
        if (!idTagAtConfigStartInitialized) {
            idTagAtConfigStart = idTag; // Store idTag value when config mode started
            idTagAtConfigStartInitialized = true;
            if (debugEnabled) {
                Serial.printf("DEBUG: Config mode started with idTag: %s\n", idTagAtConfigStart.c_str());
            }
        }
        
        // Only end config mode if:
        // 1. idTag has a value
        // 2. idTag is different from what it was when config mode started (means new RFID tag detected)
        if (idTag.length() > 0 && idTag != idTagAtConfigStart) {
            idTagAtConfigStartInitialized = false; // Reset for next config mode entry
            Serial.println("\nINFO: RFID tag detected. Ending configuration mode and switching to normal operation.");
            
            // Note: Tag detected tone is already played in RFID_MFRC522_loop_handler() for every tag detection
            
            // NOTE: Do NOT save the detected RFID tag to NVS - it should only be used temporarily
            // The default_id_tag from Config-GUI or Server config should remain unchanged
            // The RFID tag will be used temporarily in RAM to start counting pulses immediately
            
            if (debugEnabled) {
                Serial.printf("DEBUG: Using RFID tag temporarily (not saving to NVS): %s\n", idTag.c_str());
                Serial.println("DEBUG: Default-ID-Tag remains unchanged in NVS");
            }

            #ifdef ENABLE_OLED
            display.clearBuffer();
            display.setFont(u8g2_font_7x14_tf);
            display.drawStr(20, 12, "ID Tag erkannt!");
            display.drawStr(20, 28, idTag.c_str());
            display.drawStr(20, 44, "Wechsel zu");
            display.drawStr(20, 60, "Normalbetrieb");
            display.sendBuffer();
            delay(2000);
            #endif
            
            // Stop config server
            server.stop();
            if (debugEnabled) {
                Serial.println("DEBUG: Config server stopped");
            }
            
            // Disconnect WiFi AP
            WiFi.softAPdisconnect(true);
            if (debugEnabled) {
                Serial.println("DEBUG: WiFi AP disconnected");
            }
            
            // Switch WiFi mode to Station only
            WiFi.mode(WIFI_STA);
            
            // End configuration mode
            configMode = false;
            
            // Connect to WiFi and start normal operation
            if (debugEnabled) {
                Serial.println("DEBUG: Connecting to WiFi and starting normal operation...");
            }
            connectToWiFi();
            
            // Reset lastSentIdTag so the RFID tag is recognized as new and counting starts immediately
            lastSentIdTag = "";
            
            // Continue with normal operation (no restart needed)
            // The RFID tag in idTag will be used immediately for pulse counting
            return; // Exit config mode handling, continue with normal mode in next loop iteration
        }

        // --- End configuration mode on timeout ---
        if (millis() - configModeStartTime >= configModeTimeout_sec * 1000) {
            // Check if critical configurations are still missing
            // Reload preferences to check current state (user might have saved config)
            preferences.begin("bike-tacho", true); // Read-only mode
            String currentWifiSsid = preferences.getString("wifi_ssid", "");
            String currentDefaultIdTag = preferences.getString("default_id_tag", "");
            if (currentDefaultIdTag.length() == 0) {
                currentDefaultIdTag = preferences.getString("idTag", "");
            }
            // Check if DEFAULT_ID_TAG is available as fallback
            #ifdef DEFAULT_ID_TAG
            if (currentDefaultIdTag.length() == 0) {
                currentDefaultIdTag = String(DEFAULT_ID_TAG);
            }
            #endif
            float currentWheelSize = preferences.getFloat("wheel_size", 2075.0);  // Default: 26 Zoll = 2075 mm
            unsigned int currentSendInterval = preferences.getUInt("sendInterval", 0);
            preferences.end();
            
            // Check if critical configs are still missing
            // Note: serverUrl and apiKey are not critical if DEFAULT values are available
            bool stillMissingCritical = (
                currentWifiSsid.length() == 0 ||
                currentDefaultIdTag.length() == 0 ||
                currentWheelSize == 0.0 ||
                currentSendInterval == 0
            );
            
            if (stillMissingCritical) {
                // Critical configs still missing - reset timeout and stay in config mode
                configModeStartTime = millis(); // Reset timeout timer
                Serial.println("\nWARNING: Configuration mode timeout reached, but critical configurations still missing. Staying in config mode.");
                
                #ifdef ENABLE_OLED
                display.clearBuffer();
                display.setFont(u8g2_font_7x14_tf);
                display.drawStr(20, 12, "Config Timeout");
                display.drawStr(20, 28, "Bitte");
                display.drawStr(20, 44, "konfigurieren!");
                display.sendBuffer();
                delay(3000);
                #endif
                
                // Continue in config mode - don't exit
                return; // Continue config mode loop
            }
            
            // All critical configs are present - switch to normal operation
            // Reset static variables for next config mode entry
            idTagAtConfigStartInitialized = false;
            
            Serial.println("\nINFO: Configuration mode timeout reached. All critical configurations present. Switching to normal operation and connecting to server.");
            
            #ifdef ENABLE_OLED
            display.clearBuffer();
            display.setFont(u8g2_font_7x14_tf);
            display.drawStr(20, 12, "Config Timeout");
            display.drawStr(20, 28, "Wechsel zu");
            display.drawStr(20, 44, "Normalbetrieb");
            display.sendBuffer();
            delay(2000);
            #endif
            
            // Stop config server
            server.stop();
            if (debugEnabled) {
                Serial.println("DEBUG: Config server stopped");
            }
            
            // Disconnect WiFi AP
            WiFi.softAPdisconnect(true);
            if (debugEnabled) {
                Serial.println("DEBUG: WiFi AP disconnected");
            }
            
            // Switch WiFi mode to Station only
            WiFi.mode(WIFI_STA);
            
            // End configuration mode
            configMode = false;
            
            // Reload preferences to get latest values (user might have saved config)
            preferences.begin("bike-tacho", false);
            getPreferences();
            preferences.end();
            
            // Connect to WiFi and start normal operation (this will also connect to server)
            if (debugEnabled) {
                Serial.println("DEBUG: Connecting to WiFi and starting normal operation...");
            }
            connectToWiFi();
            
            // Reset lastSentIdTag so the default_id_tag is recognized as new and counting starts immediately
            lastSentIdTag = "";
            
            // Continue with normal operation (no restart needed)
            return; // Exit config mode handling, continue with normal mode in next loop iteration
        }

        // Optional: Pulse detection in config mode for quick switch to normal mode
        pcnt_get_counter_value(PCNT_UNIT, &currentPulseCount);
        if (currentPulseCount > 0) { // Pulse detected - always allow exit from config mode
            // Reset static variables for next config mode entry
            idTagAtConfigStartInitialized = false;
            
            Serial.println("\nINFO: Pulse detected. Ending configuration mode and switching to normal operation.");
            
            if (debugEnabled) {
                Serial.println("DEBUG: Pulse detected, switching to normal operation without restart");
            }

            #ifdef ENABLE_OLED
            display.clearBuffer();
            display.setFont(u8g2_font_7x14_tf);
            display.drawStr(20, 12, "Puls erkannt!");
            display.drawStr(20, 44, "Wechsel zu");
            display.drawStr(20, 60, "Normalbetrieb");
            display.sendBuffer();
            delay(2000);
            #endif
            
            // Stop config server
            server.stop();
            if (debugEnabled) {
                Serial.println("DEBUG: Config server stopped");
            }
            
            // Disconnect WiFi AP
            WiFi.softAPdisconnect(true);
            if (debugEnabled) {
                Serial.println("DEBUG: WiFi AP disconnected");
            }
            
            // Switch WiFi mode to Station only
            WiFi.mode(WIFI_STA);
            
            // End configuration mode
            configMode = false;
            
            // Connect to WiFi and start normal operation
            if (debugEnabled) {
                Serial.println("DEBUG: Connecting to WiFi and starting normal operation...");
            }
            connectToWiFi();
            
            // Reset lastSentIdTag so the default_id_tag is recognized as new and counting starts immediately
            lastSentIdTag = "";
            
            // Continue with normal operation (no restart needed)
            // Pulse counting will start immediately
            return; // Exit config mode handling, continue with normal mode in next loop iteration
        }
    } else {

        // ----------------------------------------------------------------------
        // MONITOR ID TAG CHANGE
        // ----------------------------------------------------------------------
        // Checks if the currently loaded idTag (from Preferences/NVS or RFID detection) differs from the last sent/used tag.
        // This works both with and without RFID: idTag can be loaded from NVS or detected via RFID.
        //if (idTag != lastSentIdTag && lastSentIdTag.length() > 0) {
        if (idTag.length() > 0 && idTag != lastSentIdTag) {
            // Only play tone if tag was NOT detected via RFID (to avoid double beep)
            // RFID detection already plays tone in RFID_MFRC522_loop_handler()
            if (!idTagFromRFID) {
                if (debugEnabled) {
                  Serial.println("DEBUG: play_tag_detected_tone ");
                }
                play_tag_detected_tone(); // <-- CALL: 1x long
            }
            
            resetDistanceCounters();

            // IMPORTANT CORRECTION: lastSentIdTag MUST be set to the new idTag immediately to end the infinite loop.
            lastSentIdTag = idTag;

            // QUERY USER_ID FROM SERVER AND DISPLAY ON OLED (if enabled)
            // This works independently of RFID - the server is queried for any idTag
            // Only query if WLAN is connected and API key error is not active
            if (WiFi.status() == WL_CONNECTED && !apiKeyErrorActive) {
                String newUsername = getUserIdFromTag(idTag);
                // getUserIdFromTag() returns:
                // - Valid username string if found
                // - "NULL" if user not found (HTTP 404 or server returned "NULL")
                // - "" (empty) if query failed (backoff period, connection error, etc.)
                if (newUsername.length() > 0) {
                    // Query was successful - update username (could be valid name or "NULL")
                    bool wasUsernameNull = (username.length() == 0 || username == "NULL");
                    bool isUsernameNull = (newUsername == "NULL");
                    bool usernameChanged = (wasUsernameNull != isUsernameNull) || (username != newUsername);
                    
                    if (usernameChanged) {
                        username = newUsername;
            
            #ifdef ENABLE_OLED
                        // Always update display when ID tag changes (new query was made)
                        // queryWasSuccessful = true because newUsername.length() > 0 means query was successful
                        // Note: If HTTP 404, username was already set to "NULL" in getUserIdFromTag() and error was already shown
            if (username.length() > 0 && username != "NULL") {
                            display_IdTag_Name(username.c_str(), idTagFromRFID, true);
            } else {
                            // HTTP 404 - error message was already shown in getUserIdFromTag(), don't overwrite it
                            // Just keep the "Radler nicht gefunden" message that was already displayed
            }
            delay(3000);
            #endif
                    }
        }  
                // If newUsername is empty, query failed - don't update username, keep previous value
            } else {
                // WLAN not connected or API key error is active - don't query username
                if (debugEnabled) {
                    if (WiFi.status() != WL_CONNECTED) {
                        Serial.println("DEBUG: WLAN not connected, skipping username query.");
                    } else {
                        Serial.println("DEBUG: API key error active, skipping username query.");
                    }
                }
            }

        }
        
        // Check if username is valid - if not, don't send data to server
        // Also don't send if API key error is active
        bool hasValidUsername = (!apiKeyErrorActive && username.length() > 0 && username != "NULL");  

        if (WiFi.status() != WL_CONNECTED) {
            // Only try to reconnect if we haven't exceeded 3 attempts
            if (wifiConnectAttempts < 3) {
            // Connection is disconnected: TRY TO RESTORE CONNECTION
            connectToWiFi(); 
            } else {
                // Already tried 3 times, don't retry (error message already shown)
                if (debugEnabled && (millis() % 60000 < 100)) { // Log every ~60 seconds
                    Serial.println("DEBUG: WiFi connection failed after 3 attempts. Not retrying.");
                }
            }
        } else {
            // WiFi is connected - reset attempt counter and update display if error was shown
            bool hadWifiError = (wifiConnectAttempts >= 3);
            if (wifiConnectAttempts > 0) {
                wifiConnectAttempts = 0;
              if (debugEnabled) {
                    Serial.println("DEBUG: WiFi connection restored. Resetting attempt counter.");
              }
                
                // Update display if WiFi error was just resolved
                if (hadWifiError) {
                    #ifdef ENABLE_OLED
                    // Show normal display (username or default message) - WiFi error is resolved
                    // queryWasSuccessful = false because we're just showing the current username, no new query was made
                    if (username.length() > 0 && username != "NULL") {
                        display_IdTag_Name(username.c_str(), idTagFromRFID, false);
                    } else {
                        display_IdTag_Name("NULL", idTagFromRFID, false);
                    }
                    #endif
                }
            }
        }
        
        // Note: Heartbeat is only sent:
        // 1. At first start (after WiFi connection in connectToWiFi)
        // 2. After wakeup from deep sleep (in setup, when wakeup_reason == ESP_SLEEP_WAKEUP_EXT0)
        // This reduces the number of heartbeats and server load
        
        // Note: Firmware checks are done:
        // 1. After WiFi connection (in setup/connectToWiFi)
        // 2. Before deep sleep (below, when no pulses detected)
        // This avoids interrupting active pulse data collection
    
        // Only count pulses if data can be sent (valid username and no API key error)
        // Block pulse counting if errors are active, as it makes no sense to count pulses that cannot be sent
        if (hasValidUsername) {
        // Query counter value and output in log, but only on change
        pcnt_get_counter_value(PCNT_UNIT, &currentPulseCount);
        //if (debugEnabled) {
        //      Serial.printf("Pulse detected! Current Pulse Count: %d\n", currentPulseCount);
        //}
        //delay(1);

            if (currentPulseCount != lastPulseCount) {
            // Total distance is still updated, but not sent
            // wheel_size is in mm, so result is in mm
            totalDistance_mm = (float)currentPulseCount * wheel_size;

            // Calculate current speed based on time between pulses
            unsigned long currentTime = millis();
            if (previousPulseTime > 0) {
                // Calculate time difference in milliseconds
                unsigned long timeSinceLastPulse_ms = currentTime - previousPulseTime;
                float newSpeed = 0.0;
                if (timeSinceLastPulse_ms > 0 && timeSinceLastPulse_ms < SPEED_TIMEOUT_MS) {
                    // Speed calculation: (wheel_size_mm / time_ms) * 3.6
                    // Formula: (mm/ms) * (1000 ms/s) * (3600 s/h) / (1000000 mm/km) = (mm/ms) * 3.6
                    newSpeed = (wheel_size / (float)timeSinceLastPulse_ms) * 3.6;
                    if (debugEnabled) {
                        Serial.printf("DEBUG: Speed calculated: %.1f km/h (time between pulses: %lu ms)\n", newSpeed, timeSinceLastPulse_ms);
                    }
                } else {
                    // Timeout or invalid time - set speed to 0
                    newSpeed = 0.0;
                }
                
                // Add new speed value to history array (rolling average)
                speedHistory[speedHistoryIndex] = newSpeed;
                speedHistoryIndex = (speedHistoryIndex + 1) % SPEED_AVERAGE_COUNT; // Circular buffer
                if (speedHistoryCount < SPEED_AVERAGE_COUNT) {
                    speedHistoryCount++; // Increment count until we have 5 values
                }
                
                // Calculate average of last 5 speed values
                float speedSum = 0.0;
                for (int i = 0; i < speedHistoryCount; i++) {
                    speedSum += speedHistory[i];
                }
                currentSpeed_kmh = speedSum / (float)speedHistoryCount;
                
                if (debugEnabled) {
                    Serial.printf("DEBUG: Speed average (last %d pulses): %.1f km/h\n", speedHistoryCount, currentSpeed_kmh);
                }
            }
            previousPulseTime = currentTime; // Store current time for next pulse calculation

            if (debugEnabled) {
              Serial.printf("DEBUG: Pulse detected! currentPulseCount: %d | totalDistance_mm: %.1f mm\n", currentPulseCount, totalDistance_mm);
            }
            lastPulseCount = currentPulseCount;
            lastPulseTime = currentTime; // Update the timestamp of the last pulse for Deep Sleep
            
            #ifdef ENABLE_OLED
            display_Data();
            #endif

            // Let LED briefly blink on counted pulse
            if (ledEnabled) {
                //ledIsOn = true;
                //ledOnTime = millis();
                digitalWrite(LED_PIN, HIGH);
                delay(50);
                //ledIsOn = false;
                digitalWrite(LED_PIN, LOW);
                }
            }
        } else {
            // Block pulse counting when errors are active
            // Don't read counter value to prevent counting pulses that cannot be sent
            if (debugEnabled && (millis() % 10000 < 100)) { // Log every ~10 seconds
                if (WiFi.status() != WL_CONNECTED) {
                    Serial.println("DEBUG: Pulse counting blocked - WLAN not connected");
                } else if (apiKeyErrorActive) {
                    Serial.println("DEBUG: Pulse counting blocked - API key error active");
                } else {
                    Serial.println("DEBUG: Pulse counting blocked - no valid username assigned");
                }
            }
        }
        
        // Periodic config fetch (even when Deep Sleep is disabled)
        // Also fetches on first start (lastConfigFetchTime == 0) or when interval is reached
        // Don't fetch if API key error is active (must fix API key first)
        if (configFetchInterval_sec > 0) {
            if (WiFi.status() == WL_CONNECTED && !apiKeyErrorActive) {
                unsigned long elapsed_ms = (lastConfigFetchTime == 0) ? 0 : (millis() - lastConfigFetchTime);
                bool shouldFetch = (lastConfigFetchTime == 0) || (elapsed_ms >= (unsigned long)configFetchInterval_sec * 1000);
                
                if (debugEnabled && shouldFetch) {
                    if (lastConfigFetchTime == 0) {
                        Serial.println("DEBUG: Periodic config fetch - first fetch after startup");
                    } else {
                        Serial.printf("DEBUG: Periodic config fetch triggered (interval: %u s, elapsed: %lu s)\n", 
                            configFetchInterval_sec, elapsed_ms / 1000);
                    }
                }
                
                if (shouldFetch) {
                    if (fetchDeviceConfig()) {
                        lastConfigFetchTime = millis();
                        if (debugEnabled) {
                            Serial.printf("DEBUG: Config fetched successfully. Next fetch in %u seconds\n", configFetchInterval_sec);
                        }
                    } else {
                        if (debugEnabled) {
                            Serial.println("DEBUG: Config fetch failed, will retry on next interval");
                        }
                        // Don't update lastConfigFetchTime on failure, so it retries sooner
                    }
                }
            } else {
                if (debugEnabled && (millis() % 60000 < 100)) { // Log every ~60 seconds
                    if (apiKeyErrorActive) {
                        Serial.println("DEBUG: Periodic config fetch skipped - API key error active (must fix API key first)");
                    } else {
                Serial.printf("DEBUG: Periodic config fetch skipped - WiFi not connected (interval: %u s)\n", configFetchInterval_sec);
                    }
                }
            }
        }
        
        // Logic for normal send mode
        // Only send data if username is valid (assigned on server)
        if (!testActive && hasValidUsername && (millis() - lastDataSendTime >= (unsigned long)sendInterval_sec * 1000)) {
           if (debugEnabled) {
              Serial.println("DEBUG: Sending data");
            }
            // Calculate distance traveled and speed in last interval
            //pcnt_get_counter_value(PCNT_UNIT, &currentPulseCount);
            int16_t pulsesInInterval = currentPulseCount - pulsesAtLastSend;
            // wheel_size is in mm, so result is in mm
            distanceInInterval_mm = (float)pulsesInInterval * wheel_size;
            if (debugEnabled) {
              Serial.printf("DEBUG: pulsesInInterval: %d | distanceInInterval_mm: %.1f mm\n", pulsesInInterval, distanceInInterval_mm);
            }
            // Convert speed from mm/s to km/h: (mm/s) * (3600 s/h) / (1000000 mm/km) = (mm/s) * 0.0036
            speed_kmh = (distanceInInterval_mm / (float)sendInterval_sec) * 0.0036;
            
            // Send data only if distance has changed
            if (distanceInInterval_mm > 0) {
              if (debugEnabled) {
                Serial.println("DEBUG: Sending real data after interval elapsed.");
              }             

              int responseCode =  sendDataToServer(speed_kmh, distanceInInterval_mm, pulsesInInterval, false);
              
              if (responseCode > 0 && responseCode < 300) { // HTTP status codes 2xx are usually successful
                    lastDataSendTime = millis();
                    pulsesAtLastSend = currentPulseCount;
                    // Update lastSentIdTag here since data was sent successfully
                    lastSentIdTag = idTag;
                    // Clear server error backoff on success
                    bool hadServerError = (lastServerErrorTime > 0);
                    lastServerErrorTime = 0;
                    // Clear API key error flag on successful communication
                    bool wasApiKeyError = apiKeyErrorActive;
                    apiKeyErrorActive = false;
                    
                    // Update display if any error was just resolved (API key, WLAN, Wartung, Server)
                    if (wasApiKeyError || hadServerError) {
                        #ifdef ENABLE_OLED
                        // Show normal display (username or default message) - error is resolved
                        // queryWasSuccessful = false because we're just showing the current username, no new query was made
                        if (username.length() > 0 && username != "NULL") {
                            display_IdTag_Name(username.c_str(), idTagFromRFID, false);
                        } else {
                            display_IdTag_Name("NULL", idTagFromRFID, false);
                        }
                        #endif
                    }

                    if (debugEnabled) {
                        Serial.printf("DEBUG: Data sent successfully! Status: %d\n", responseCode);
                    }
                } else if (responseCode == -1) {
                    // WiFi error: No update of send time so it tries faster next time.
                    digitalWrite(LED_PIN, LOW);
                    if (debugEnabled) {
                        Serial.println("DEBUG: Send failed: No WiFi.");
                    }
                } else {
                    // Other error (e.g. HTTP 4xx/5xx, internal error)
                    // Update backoff timer
                    lastServerErrorTime = millis();
                    digitalWrite(LED_PIN, LOW);
                    
                    // Show error on display
                    String errorType = "Server";
                    bool isApiKeyError = false;
                    if (responseCode == 401 || responseCode == 403) {
                        errorType = "API Key";
                        isApiKeyError = true;
                    } else if (responseCode == 503) {
                        errorType = "Wartung";
                    }
                    
                    // Set API key error flag if API key error detected
                    if (isApiKeyError) {
                        apiKeyErrorActive = true;
                    }
                    
                    #ifdef ENABLE_OLED
                    display_ServerError(errorType.c_str(), responseCode);
                    delay(2000);
                    // Ensure LED stays off after error display
                    digitalWrite(LED_PIN, LOW);
                    #endif
                    
                    if (debugEnabled) {
                        Serial.printf("DEBUG: Send failed: Code %d. Waiting for next attempt.\n", responseCode);
                    }
              }
                
            }
            lastDataSendTime = millis();
        } else if (!testActive && !hasValidUsername && (millis() - lastDataSendTime >= (unsigned long)sendInterval_sec * 1000)) {
            // No valid username - skip sending but update timer to avoid spamming
            // Retry after backoff period, even if API key error is active (to check if API key was fixed)
            if (lastServerErrorTime == 0 || (millis() - lastServerErrorTime) >= serverErrorBackoffInterval) {
                // Only query if WLAN is connected
                if (WiFi.status() == WL_CONNECTED) {
                    if (debugEnabled) {
                        if (apiKeyErrorActive) {
                            Serial.println("DEBUG: Retrying connection after backoff period to check if API key error is resolved.");
                        } else {
                            Serial.println("DEBUG: Retrying username query after backoff period.");
                        }
                    }
                    String newUsername = getUserIdFromTag(idTag);
                    // getUserIdFromTag() returns:
                    // - Valid username string if found
                    // - "NULL" if user not found (HTTP 404 or server returned "NULL")
                    // - "" (empty) if query failed (backoff period, connection error, etc.)
                    if (newUsername.length() > 0) {
                        // Query was successful - update username (could be valid name or "NULL")
                        bool wasUsernameNull = (username.length() == 0 || username == "NULL");
                        bool isUsernameNull = (newUsername == "NULL");
                        bool usernameChanged = (wasUsernameNull != isUsernameNull) || (username != newUsername);
                        
                        if (usernameChanged) {
                            username = newUsername;
                            
                            #ifdef ENABLE_OLED
                            // Show updated display (username or default message)
                            // queryWasSuccessful = true because newUsername.length() > 0 means query was successful
                            // Note: If HTTP 404, username was already set to "NULL" in getUserIdFromTag() and error was already shown
                            if (username.length() > 0 && username != "NULL") {
                                display_IdTag_Name(username.c_str(), idTagFromRFID, true);
                            } else {
                                // HTTP 404 - error message was already shown in getUserIdFromTag(), don't overwrite it
                                // Just keep the "Radler nicht gefunden" message that was already displayed
                            }
                            #endif
                        }
                    }
                    // If newUsername is empty, query failed - don't update username, keep previous value
                }
            } else {
                if (debugEnabled) {
                    if (apiKeyErrorActive) {
                        Serial.println("DEBUG: Skipping connection retry - still in backoff period (API key error active).");
                    } else {
                        Serial.println("DEBUG: Skipping data send - no valid username assigned on server (in backoff period).");
                    }
                }
            }
            lastDataSendTime = millis();
        }

        // Deep Sleep Check - only if deepSleepTimeout_sec > 0 (0 = disabled)
        if ( deepSleepTimeout_sec > 0 && (millis() - lastPulseTime >= (unsigned long)deepSleepTimeout_sec * 1000) && DeepSleep ) {
          if (debugEnabled) {
              Serial.println("DEBUG: Deep Sleep check ...");
              Serial.printf("DEBUG: deepSleepTimeout_sec= %d.\n", deepSleepTimeout_sec);
          }
          
          // Check for firmware update before going to sleep
          // This ensures we don't miss updates when device is inactive
          if (WiFi.status() == WL_CONNECTED) {
              if (debugEnabled) {
                  Serial.println("DEBUG: Checking for firmware update before deep sleep...");
              }
              if (checkFirmwareUpdate()) {
                  // Update is available, download and install
                  if (debugEnabled) {
                      Serial.println("DEBUG: Firmware update available. Starting download before sleep...");
                  }
                  downloadFirmware();
                  // Note: downloadFirmware() will restart the device on success
                  return; // Exit loop if update is being installed
              }
          }
          
          if (digitalRead(SENSOR_PIN) == HIGH) {
            if (debugEnabled) {
              Serial.println("DEBUG: Pin is HIGH. Switching to deep sleep mode.");
            }

            // --- OLED control: Turn off display ---
            #ifdef ENABLE_OLED
            if (debugEnabled) {
                Serial.println("DEBUG: Turning off OLED display.");
            }

            display.clearBuffer();
            display.setFont(u8g2_font_7x14_tf);
            display.drawStr(0, 12, "Keine Impulse mehr!");
            display.drawStr(5, 28, "Ich geh schlafen!");
            display.drawStr(30, 44, "Strampeln");  // 
            display.drawStr(10, 60, "weckt mich auf" );  // 
            display.sendBuffer();
            delay(10000);

            // 1. Put U8g2 display controller into sleep mode
            display.clearDisplay();
            display.sendBuffer(); 
            display.sleepOn();     // SSD1306 into sleep mode (Display Off)
            #endif

            // --- Heltec VEXT control: Turn off power supply (if defined) ---
            #ifdef BOARD_HELTEC
            if (debugEnabled) {
                Serial.println("DEBUG: Turning off VEXT (OLED power).");
            }
            // Set VEXT_PIN to HIGH to completely turn off display (HIGH = OFF)
            digitalWrite(VEXT_PIN, HIGH);
            #endif

            esp_sleep_enable_ext0_wakeup((gpio_num_t)SENSOR_PIN, LOW);
            esp_deep_sleep_start();
          } else {
             if (debugEnabled) {
                Serial.println("DEBUG: Pin is already LOW. Deep sleep will be delayed until pin goes HIGH.");
             }
            // Stay in loop and wait until pin goes HIGH again.
            lastPulseTime = millis();
          }  
        }
    }
}


// --- Functions for data transmission ---
/**
 * @brief Connects the ESP32 to a WiFi network using stored credentials.
 * 
 * Reads WiFi SSID and password from global variables and attempts connection.
 * Updates OLED display (if enabled) with connection status.
 * 
 * @note Hardware interaction: OLED display (if ENABLE_OLED is defined)
 * @note Side effects: Modifies WiFi state, updates OLED display, writes to Serial
 */
void connectToWiFi() {
    if (debugEnabled) {
      Serial.print("DEBUG: Connecting to WiFi ");
      Serial.println(wifi_ssid);

    }

    #ifdef ENABLE_OLED
    display.clearBuffer();
    display.setFont(u8g2_font_7x14_tf);

    textline = "MyCyclingCity";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 12); 
    display.print(textline);

    textline = deviceName.c_str();
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 28); 
    display.print(textline);

 
    textline = "Verbinde mit WLAN:";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 44); 
    display.print(textline);

    textline = wifi_ssid.c_str();
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 60); 
    display.print(textline);
 
    display.sendBuffer();
    delay(2000);
    #endif

    // Turn on LED to indicate WiFi connection activity
    digitalWrite(LED_PIN, HIGH);
    
    WiFi.begin(wifi_ssid.c_str(), wifi_password.c_str());
    int attempts = 0;
    const int MAX_ATTEMPTS = 20;  // Maximum 20 connection attempts (20 * 500ms = 10 seconds timeout)
    while (WiFi.status() != WL_CONNECTED && attempts < MAX_ATTEMPTS) {
        delay(500);
        if (debugEnabled) {
          Serial.print(".");
        }
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        // Reset connection attempt counter on successful connection
        bool hadWifiError = (wifiConnectAttempts >= 3);
        wifiConnectAttempts = 0;
        if (debugEnabled) {
          Serial.println("\nDEBUG: Connected!");
          Serial.print("DEBUG: IP address: ");
          Serial.println(WiFi.localIP());
        }
        
        // Update display if WiFi error was just resolved
        if (hadWifiError) {
            // Don't reset username here - it will be updated after successful query below
            // Keep previous username value (if any) until new query is made
            #ifdef ENABLE_OLED
            // Show normal display (username or default message) - WiFi error is resolved
            // Note: username will be queried after WiFi connection, so we show a temporary message first
            display.clearBuffer();
            display.setFont(u8g2_font_7x14_tf);
            
            textline = "WLAN verbunden";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 28);
            display.print(textline);
            
            display.sendBuffer();
            delay(1000);  // Brief display of connection message
            #endif
        }
        
        // Report device configuration to server after successful WiFi connection
        // This allows the server to detect configuration differences
        if (debugEnabled) {
          Serial.println("DEBUG: Reporting device configuration to server...");
        }
        bool configReported = reportDeviceConfig();
        if (debugEnabled) {
            Serial.printf("DEBUG: reportDeviceConfig() returned: %s\n", configReported ? "true" : "false");
        }
        
        // Fetch server-side configuration if available
        // Only fetch if config was successfully reported (server is reachable)
        if (configReported) {
            if (debugEnabled) {
                Serial.println("DEBUG: Fetching server-side configuration after WiFi connection...");
            }
            bool fetchSuccess = fetchDeviceConfig();
            if (fetchSuccess) {
                lastConfigFetchTime = millis();
                if (debugEnabled) {
                    Serial.println("DEBUG: Config fetched successfully after WiFi connection");
                }
            } else {
                if (debugEnabled) {
                    Serial.println("DEBUG: Config fetch failed after WiFi connection, will retry later");
                }
            }
        } else {
            if (debugEnabled) {
                Serial.println("DEBUG: Skipping fetchDeviceConfig() because reportDeviceConfig() returned false");
            }
        }
        
        // Check for firmware update immediately after WiFi connection
        // This ensures firmware check happens even if device goes to sleep soon
        if (debugEnabled) {
            Serial.println("DEBUG: Checking for firmware update after WiFi connection...");
        }
        bool updateAvailable = checkFirmwareUpdate();
        if (debugEnabled) {
            Serial.printf("DEBUG: checkFirmwareUpdate() returned: %s\n", updateAvailable ? "true" : "false");
        }
        if (updateAvailable) {
            // Update is available, download and install
            if (debugEnabled) {
                Serial.println("DEBUG: Firmware update available. Starting download...");
            }
            bool downloadSuccess = downloadFirmware();
            if (debugEnabled) {
                Serial.printf("DEBUG: downloadFirmware() returned: %s\n", downloadSuccess ? "true" : "false");
            }
            // Note: downloadFirmware() will restart the device on success
        } else {
            if (debugEnabled) {
                Serial.println("DEBUG: No firmware update available or check failed.");
            }
        }
        
        // Send heartbeat at first start (only if not woken from deep sleep)
        // Note: wakeup_reason is checked here because connectToWiFi() is called from both
        // first start and wakeup scenarios, but we only want heartbeat at first start here
        esp_sleep_wakeup_cause_t wakeup_reason_check = esp_sleep_get_wakeup_cause();
        if (wakeup_reason_check != ESP_SLEEP_WAKEUP_EXT0) {
            // This is first start, not wakeup from deep sleep
            if (debugEnabled) {
                Serial.println("DEBUG: Sending heartbeat at first start...");
            }
            sendHeartbeat();  // LED is controlled inside sendHeartbeat()
        }
        // Note: If wakeup from deep sleep, heartbeat is sent in setup() after connectToWiFi()

        // Turn off LED after all WiFi activities are complete
        digitalWrite(LED_PIN, LOW);

        #ifdef ENABLE_OLED
        display.clearBuffer();
        display.setFont(u8g2_font_7x14_tf);

        textline = "MyCyclingCity";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 12);
        display.print(textline);

        textline = deviceName.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 28);
        display.print(textline);

        textline = "Verbunden mit:";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 44);
        display.print(textline);

        textline = wifi_ssid.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 60);
        display.print(textline);

        display.sendBuffer();
        delay(2000);
        #endif

        // Query username from server after successful WiFi connection
        // Only query if WLAN is connected
        if (idTag.length() > 0 && WiFi.status() == WL_CONNECTED) {
            String newUsername = getUserIdFromTag(idTag);
            // getUserIdFromTag() returns:
            // - Valid username string if found
            // - "NULL" if user not found (HTTP 404 or server returned "NULL")
            // - "" (empty) if query failed (backoff period, connection error, etc.)
            if (newUsername.length() > 0) {
                // Query was successful - update username (could be valid name or "NULL")
                bool wasUsernameNull = (username.length() == 0 || username == "NULL");
                bool isUsernameNull = (newUsername == "NULL");
                bool usernameChanged = (wasUsernameNull != isUsernameNull) || (username != newUsername);
                
                username = newUsername;
                
                // Always update display after successful query (especially after WLAN reconnection)
                // queryWasSuccessful = true because newUsername.length() > 0 means query was successful
                // Note: If HTTP 404, username was already set to "NULL" in getUserIdFromTag() and error was already shown
                #ifdef ENABLE_OLED
                if (username.length() > 0 && username != "NULL") {
                    display_IdTag_Name(username.c_str(), idTagFromRFID, true);
    } else {
                    // HTTP 404 - error message was already shown in getUserIdFromTag(), don't overwrite it
                    // Just keep the "Radler nicht gefunden" message that was already displayed
                }
                #endif
            }
            // If newUsername is empty, query failed - don't update username, keep previous value
            if (debugEnabled) {
                if (newUsername.length() > 0) {
                    if (username.length() > 0 && username != "NULL") {
                        Serial.printf("DEBUG: Username queried on WiFi connect: %s\n", username.c_str());
                    } else {
                        Serial.println("DEBUG: No username assigned on server for this tag.");
                    }
                } else {
                    Serial.println("DEBUG: Username query failed (backoff or connection error).");
                }
            }
        }

    } else {
        // Increment connection attempt counter
        wifiConnectAttempts++;
        
        if (debugEnabled) {
          Serial.println("\nDEBUG: Connection failed.");
          Serial.printf("DEBUG: WiFi connection attempt %d of 3\n", wifiConnectAttempts);
        }
        
        // Show error message after 3 failed attempts
        if (wifiConnectAttempts >= 3) {
        #ifdef ENABLE_OLED
        display.clearBuffer();
        display.setFont(u8g2_font_7x14_tf);
            
            textline = "Fehler:";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 12);
            display.print(textline);
            
            textline = "Keine";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 28);
            display.print(textline);
            
            textline = "WLAN-Verbindung";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 44);
            display.print(textline);
            
            display.sendBuffer();
            #endif
            digitalWrite(LED_PIN, LOW);
            
            if (debugEnabled) {
                Serial.println("DEBUG: WiFi connection failed after 3 attempts. Showing error message.");
            }
        }
        
        #ifdef ENABLE_OLED
        // Only show "keine Verbindung" message if we haven't already shown the error after 3 attempts
        if (wifiConnectAttempts < 3) {
            display.clearBuffer();
            display.setFont(u8g2_font_7x14_tf);

        textline = "MyCyclingCity";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 12);
        display.print(textline);

        textline = deviceName.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 28);
        display.print(textline);

        textline = "keine Verbindung:";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 44); 
        display.print(textline);

        textline = wifi_ssid.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 60);
        display.print(textline);

        display.sendBuffer();
        delay(2000); 
        }
        #endif
        
        // Turn off LED on connection failure
        digitalWrite(LED_PIN, LOW);
    }
    
    // Turn off LED after all WiFi activities are complete (if not already turned off)
    // Note: LED is already turned off in the else block above, but we ensure it's off here too
    digitalWrite(LED_PIN, LOW);
}

/**
 * @brief Sends tachometer data to the configured server via HTTP POST.
 * 
 * Sends distance, speed, and pulse data as JSON to the server API endpoint.
 * Handles both test mode (simulated data) and normal mode (real measurements).
 * 
 * @param currentSpeed_kmh Current speed in kilometers per hour
 * @param distanceInInterval_mm Distance traveled in the interval in millimeters
 * @param pulsesInInterval Number of pulses detected in the interval
 * @param isTest If true, sends simulated test data instead of real measurements
 * @return HTTP status code on success (>0), -1 on WiFi error, -2 on configuration error
 * 
 * @note Hardware interaction: LED_PIN (blinks during transmission)
 * @note Side effects: Sends HTTP request, controls LED, writes to Serial
 */
int sendDataToServer(float currentSpeed_kmh, float distanceInInterval_mm, int pulsesInInterval, bool isTest) {
  if (serverUrl.length() == 0 || wifi_ssid.length() == 0) {
    digitalWrite(LED_PIN, LOW);  // Turn off LED on error
    if (debugEnabled) {
      Serial.println("DEBUG: Error: Server URL or WiFi SSID is not configured.");
    }
    return -2;
  }

  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_PIN, LOW);  // Turn off LED on error
    if (debugEnabled) {
      Serial.println("DEBUG: sendDataToServer: ERROR: No WiFi connected.");
    }
    return -1;
  }
  
  HTTPClient http;
  StaticJsonDocument<200> doc;

  if (isTest) {
    if (debugEnabled) {
      Serial.print("DEBUG: Sending test data. Simulated distance: ");
      Serial.print(testDistance);
      Serial.println(" km");
    }
    char distanceStr[10];
    snprintf(distanceStr, sizeof(distanceStr), "%.2f", testDistance);
    doc["distance"] = distanceStr;
  } else {
      float distanceInInterval_km = distanceInInterval_mm / 1000000.0;  // Convert mm to km
      if (debugEnabled) {
        Serial.println("DEBUG: Sending real data.");
        Serial.printf("DEBUG: Speed: %.2f km/h, Distance: %.6f km, Pulses: %d\n", currentSpeed_kmh, distanceInInterval_km, pulsesInInterval);
      }
      doc["distance"] = distanceInInterval_km;
  }
  
  String finalDeviceId = deviceName;
  if (finalDeviceId.length() > 0) {
    finalDeviceId += deviceIdSuffix;
  }
  
  doc["device_id"] = finalDeviceId;

  // Overwrite ID tag for test mode
  if (isTest) {
      doc["id_tag"] = "MCC-Testuser" + deviceIdSuffix;
      if (debugEnabled) {
        Serial.printf("DEBUG: In test mode, ID tag is overwritten: %s\n", doc["id_tag"].as<String>().c_str());
      }
  } else {
      doc["id_tag"] = idTag;
  }

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  // Combine base URL + specific path ---
  String finalUrl = serverUrl;
  
  // Ensure base URL doesn't end with slash before appending path
  if (finalUrl.endsWith("/")) {
    finalUrl.remove(finalUrl.length() - 1);
  }
  
  // Use UPDATE_DATA path for sending tachometer data
  finalUrl += API_UPDATE_DATA_PATH;

  if (debugEnabled) {
    Serial.print("DEBUG: Sending to URL: ");
    Serial.println(finalUrl);
    
    // Display current send interval in log
    if (isTest) {
      Serial.printf("Test send interval: %u s\n", testInterval_sec);
    } else {
      Serial.printf("Send interval: %u s\n", sendInterval_sec);
    }

    // Display current wheel circumference in log
    Serial.printf("Wheel circumference: %.1f mm\n", wheel_size);

    Serial.println("Sending JSON data:");
    Serial.println(jsonPayload);
  }

  http.begin(finalUrl);
  http.addHeader("Content-Type", "application/json");
  if (apiKey.length() > 0) {
    if (debugEnabled) {
      Serial.print("Using API key header: X-Api-Key: ");
      Serial.println(apiKey);
    }
    http.addHeader("X-Api-Key", apiKey);
  }
  
  digitalWrite(LED_PIN, HIGH);  // Turn on LED when sending
    
  int httpCode = http.POST(jsonPayload);

  digitalWrite(LED_PIN, LOW);  // OFF

  if (debugEnabled) {
    Serial.printf("HTTP Code: %d\n", httpCode);
    if (httpCode > 0) {
      String response = http.getString();
      Serial.println("Server Response:");
      Serial.println(response);
    } else {
      Serial.printf("HTTP error: %s\n", http.errorToString(httpCode).c_str());
    }
  }

  http.end();

  return httpCode; // Return HTTP code (e.g. 200, 400, -11)
}


/**
 * @brief Queries the backend server to retrieve username for a given RFID tag ID.
 * 
 * Sends HTTP POST request to API_GET_USER_ID_PATH endpoint with the tag ID.
 * Parses JSON response to extract user_id field.
 * 
 * @param tagId Reference to String containing the RFID tag UID in hex format
 * @return String containing username if found, "NULL" if not found or on error, "FEHLER" on JSON parse error
 * 
 * @note Pure logic function - network communication only
 * @note Side effects: Sends HTTP request, writes to Serial
 */
String getUserIdFromTag(String& tagId) {
    // Check backoff interval - don't spam server with requests after errors
    // After 60 seconds, retry even if API key error is active (to check if API key was fixed)
    if (lastServerErrorTime > 0 && (millis() - lastServerErrorTime) < serverErrorBackoffInterval) {
        if (debugEnabled) {
            Serial.println("DEBUG: getUserIdFromTag: Still in backoff period, skipping request.");
        }
        // Return empty string to indicate query was not attempted (not just "not found")
        return "";
    }
    
    if (serverUrl.length() == 0 || wifi_ssid.length() == 0 || WiFi.status() != WL_CONNECTED) {
        if (debugEnabled) {
            Serial.println("DEBUG: getUserIdFromTag: Error: No connection or configuration error.");
        }
        // Don't show error message here - WLAN error is shown in connectToWiFi() after 3 failed attempts
        digitalWrite(LED_PIN, LOW);
        // Return empty string to indicate query was not attempted (not just "not found")
        return "";
    }

    HTTPClient http;
    StaticJsonDocument<100> doc;
    
    doc["id_tag"] = tagId;
    String jsonPayload;
    serializeJson(doc, jsonPayload);

    // Combine base URL + specific path
    String finalUrl = serverUrl;
    if (finalUrl.endsWith("/")) {
        finalUrl.remove(finalUrl.length() - 1);
    }
    finalUrl += API_GET_USER_ID_PATH;

    if (debugEnabled) {
        Serial.print("DEBUG: Querying user_id from: ");
        Serial.println(finalUrl);
        Serial.printf("DEBUG: For ID tag: %s\n", tagId.c_str());
    }

    http.begin(finalUrl);
    http.addHeader("Content-Type", "application/json");
    // Add API key header
    if (apiKey.length() > 0) {
        http.addHeader("X-Api-Key", apiKey);
    }
    
    int httpCode = http.POST(jsonPayload);
    String response = "";
    
    if (httpCode > 0) {
        if (httpCode == HTTP_CODE_OK) { // 200
            response = http.getString();
            if (debugEnabled) {
                Serial.printf("DEBUG: Server response: %s\n", response.c_str());
            }

            StaticJsonDocument<200> responseDoc;
            DeserializationError error = deserializeJson(responseDoc, response);

            if (error) {
                if (debugEnabled) {
                    Serial.printf("DEBUG: JSON deserialization error: %s\n", error.c_str());
                }
                http.end();
                return "FEHLER";
            }
            
            // Response should contain a JSON object with key "user_id"
            if (responseDoc.containsKey("user_id")) {
                String userId = responseDoc["user_id"].as<String>();
                http.end();
                // Clear server error backoff on success
                bool hadServerError = (lastServerErrorTime > 0);
                lastServerErrorTime = 0;
                // Clear API key error flag on successful communication
                bool wasApiKeyError = apiKeyErrorActive;
                apiKeyErrorActive = false;
                
                // Update username variable only if userId is not empty
                // userId can be a valid username or "NULL" if not found
                bool wasUsernameNull = (username.length() == 0 || username == "NULL");
                bool isUsernameNull = (userId.length() == 0 || userId == "NULL");
                bool usernameChanged = (wasUsernameNull != isUsernameNull) || (username != userId);
                
                if (userId.length() > 0) {
                    username = userId;
                }
                
                // Always update display after successful query (especially after errors are resolved)
                // This ensures the error message is cleared immediately when username is successfully queried
                // queryWasSuccessful = true because userId was successfully retrieved from server
                if (wasApiKeyError || usernameChanged || hadServerError || userId.length() > 0) {
                    #ifdef ENABLE_OLED
                    // Show normal display (username or default message) - error is resolved
                    if (userId.length() > 0 && userId != "NULL") {
                        display_IdTag_Name(userId.c_str(), idTagFromRFID, true);
                    } else {
                        display_IdTag_Name("NULL", idTagFromRFID, true);
                    }
                    #endif
                }
                
                // If server returns "NULL", we return this
                return userId;
            }
            
        } else {
            // HTTP error codes
            String errorType = "Server";
            bool isApiKeyError = false;
            if (httpCode == 401) {
                errorType = "API Key";
                isApiKeyError = true;
            } else if (httpCode == 403) {
                errorType = "API Key";
                isApiKeyError = true;
            } else if (httpCode == 503) {
                errorType = "Wartung";
            } else if (httpCode == 500) {
                errorType = "Server";
            } else if (httpCode == 404) {
                // 404 in getUserIdFromTag means cyclist not found
                errorType = "Radler nicht";
            }
            
            if (debugEnabled) {
                Serial.printf("DEBUG: HTTP error when retrieving user ID: %d\n", httpCode);
                Serial.println(http.getString());
            }
            
            // Update backoff timer
            lastServerErrorTime = millis();
            
            // Set API key error flag if API key error detected
            if (isApiKeyError) {
                apiKeyErrorActive = true;
            }
            
            // Ensure LED is off before showing error (it should already be off from sendDataToServer, but make sure)
            digitalWrite(LED_PIN, LOW);
            
            // For HTTP 404, update username to "NULL" immediately and show error message
            // This ensures pulse counting is blocked immediately
            if (httpCode == 404) {
                // Update username to "NULL" immediately to block pulse counting
                username = "NULL";
                
                #ifdef ENABLE_OLED
                // Show specific message for cyclist not found
                display.clearBuffer();
                display.setFont(u8g2_font_7x14_tf);
                
                textline = "Fehler:";
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 12);
                display.print(textline);
                
                textline = "Radler nicht";
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 28);
                display.print(textline);
                
                textline = "gefunden";
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 44);
                display.print(textline);
                
                display.sendBuffer();
                delay(3000);
                #endif
                
                // Ensure LED stays off after error display
                digitalWrite(LED_PIN, LOW);
                
                http.end();
                return "NULL";
    } else {
                #ifdef ENABLE_OLED
                display_ServerError(errorType.c_str(), httpCode);
                delay(3000);
                // Ensure LED stays off after error display
                digitalWrite(LED_PIN, LOW);
                #endif
            }
            // For other HTTP errors, return empty string (query failed, don't update username)
            http.end();
            return "";
        }
    } else {
        // Connection error (httpCode < 0)
        if (debugEnabled) {
            Serial.printf("DEBUG: HTTP connection error: %s\n", http.errorToString(httpCode).c_str());
        }
        
        // Update backoff timer
        lastServerErrorTime = millis();
        // Don't set apiKeyErrorActive for connection errors (only for HTTP 401/403)
        
        #ifdef ENABLE_OLED
        display_ServerError("Server", 0);
        delay(3000);
        #endif
        digitalWrite(LED_PIN, LOW);
        
        http.end();
        // Return empty string if query was not attempted (connection error, backoff, etc.)
        // Only return "NULL" if query was actually made but user not found
        // Connection errors mean query was not attempted, so return empty string
        return ""; // Return empty string on connection errors (query not attempted)
    }

    http.end();
    // Should not reach here, but return empty string as fallback
    return "";
}
/**
 * @brief Displays all configuration values stored in NVS to Serial output.
 * 
 * Prints WiFi settings, device configuration, wheel size, server URL, and test mode settings.
 * 
 * @note Pure logic function - no hardware interaction
 * @note Side effects: Writes to Serial output
 */
void displayNVSConfig() {
    Serial.println("\n--- NVS configuration data ---");
    Serial.printf("WiFi SSID: %s\n", preferences.getString("wifi_ssid", "").c_str());
    Serial.printf("WiFi password: %s\n", preferences.getString("wifi_password", "").c_str());
    Serial.printf("Device name: %s\n", (preferences.getString("deviceName", "") + deviceIdSuffix).c_str());
    Serial.printf("ID Tag: %s\n", preferences.getString("idTag", "").c_str());
    Serial.printf("Wheel size: %.1f mm\n", preferences.getFloat("wheel_size", 2075.0));
    Serial.printf("Server URL: %s\n", preferences.getString("serverUrl", "").c_str());
    Serial.printf("API Key: %s\n", preferences.getString("apiKey", "").c_str());
    Serial.printf("Send interval: %d s\n", preferences.getUInt("sendInterval", 30));
    Serial.printf("LED enabled: %s\n", preferences.getBool("ledEnabled", true) ? "Yes" : "No");
    Serial.printf("Debug mode: %s\n", preferences.getBool("debugEnabled", false) ? "Yes" : "No");
    // NVS key max length is 15 characters, so use shorter key
    Serial.printf("Deep-Sleep-Zeit: %lu s\n", preferences.getUInt("deep_sleep", 300));
    Serial.printf("Test mode: %s\n", preferences.getBool("testModeEnabled", false) ? "Yes" : "No");
    Serial.printf("  Test distance: %.2f km\n", preferences.getFloat("testDistance", 0.01));
    Serial.printf("  Test interval: %d s\n", preferences.getUInt("testInterval", 5));
    // Config-WLAN-Passwort (nicht im Klartext aus Sicherheitsgründen)
    String apPassword = preferences.getString("ap_passwd", "");
    if (apPassword.length() > 0) {
        Serial.printf("Config-WLAN-Passwort: *** (gesetzt, %d Zeichen)\n", apPassword.length());
    } else {
        Serial.printf("Config-WLAN-Passwort: (Standard)\n");
    }
    Serial.println("------------------------------\n");
}


/**
 * @brief Configures ESP32 deep sleep wakeup trigger.
 * 
 * Sets up the sensor pin (SENSOR_PIN) as wakeup source for deep sleep mode.
 * The device will wake up when the pin goes LOW.
 * 
 * @note Hardware interaction: SENSOR_PIN (GPIO configuration for wakeup)
 * @note Side effects: Configures ESP32 sleep wakeup source
 */
void setupDeepSleep() {
    // Enable wakeup from deep sleep only via sensor pin
    // Configures ESP32 to wake up on LOW signal on sensor pin
    if (debugEnabled) {
      Serial.println("Setting up deep sleep wakeup.");
    }
    esp_sleep_enable_ext0_wakeup((gpio_num_t)SENSOR_PIN, LOW); 
}


/**
 * @brief Loads all configuration values from NVS (Non-Volatile Storage) into global variables.
 * 
 * Reads WiFi credentials, device settings, wheel size, server configuration, and test mode
 * settings from persistent storage. Falls back to build flags if NVS values are empty.
 * 
 * @note Pure logic function - reads from NVS storage
 * @note Side effects: Modifies global configuration variables, writes to Serial
 */
void getPreferences() {
    // Load debug status first to immediately take control of serial output
    // Use global default value (true) as fallback if NVS is empty.
    debugEnabled = preferences.getBool("debugEnabled", debugEnabled); 
    
    // ***************************************************************
    // ADD DEBUG CHECK
    // ***************************************************************
    if (debugEnabled) {
        Serial.println("DEBUG: getPreferences() started.");
    }
    // Load saved configuration into global variables
    //preferences.begin("bike-tacho", false);
    wifi_ssid = preferences.getString("wifi_ssid", "");
    wifi_password = preferences.getString("wifi_password", "");
    deviceName = preferences.getString("deviceName", "");
    
    // Fallback to build flag DEFAULT_DEVICE_NAME if NVS is empty
    // Note: deviceIdSuffix is already generated in setup() before getPreferences() is called
    #ifdef DEFAULT_DEVICE_NAME
    if (deviceName.length() == 0) {
        deviceName = String(DEFAULT_DEVICE_NAME);
        // Write default device name to NVS so it's available on next startup
        if (!preferences.putString("deviceName", deviceName)) {
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'deviceName' to NVS\n");
        }
        if (debugEnabled) {
            Serial.print("DEBUG: Using build flag DEFAULT_DEVICE_NAME as fallback and saving to NVS: ");
            Serial.println(deviceName);
        }
    }
    #endif
    
    // Load default_id_tag from NVS (set via Config-GUI or Server config)
    // This is the default that should NOT be overwritten by RFID tag detection
    String defaultIdTag = preferences.getString("default_id_tag", "");
    // If default_id_tag doesn't exist, try legacy "idTag" key for backward compatibility
    if (defaultIdTag.length() == 0) {
        defaultIdTag = preferences.getString("idTag", "");
        // If found in legacy key, migrate to new key
        if (defaultIdTag.length() > 0) {
            if (!preferences.putString("default_id_tag", defaultIdTag)) {
                Serial.print("ERROR: getPreferences() - Failed to write parameter 'default_id_tag' to NVS\n");
            }
        }
    }
    // Fallback to build flag DEFAULT_ID_TAG if NVS is empty
    #ifdef DEFAULT_ID_TAG
    if (defaultIdTag.length() == 0) {
        defaultIdTag = String(DEFAULT_ID_TAG);
        // Write default ID tag to NVS so it's available on next startup
        if (!preferences.putString("default_id_tag", defaultIdTag)) {
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'default_id_tag' to NVS\n");
        }
        if (debugEnabled) {
            Serial.print("DEBUG: Using build flag DEFAULT_ID_TAG as fallback and saving to NVS: ");
            Serial.println(defaultIdTag);
        }
    }
    #endif
    
    idTag = defaultIdTag; // Start with default, RFID tags will override temporarily in RAM only
    
    // Reset lastSentIdTag on wakeup/startup to ensure default_id_tag is recognized as new
    // This is important after deep sleep wakeup, as the default_id_tag should be used
    // even if a different RFID tag was used before deep sleep
    lastSentIdTag = "";
    wheel_size = preferences.getFloat("wheel_size", 2075.0);  // Default: 26 Zoll = 2075 mm
    serverUrl = preferences.getString("serverUrl", "");
    // Check if apiKey exists in NVS before reading to avoid error log
    if (preferences.isKey("apiKey")) {
        apiKey = preferences.getString("apiKey", "");
    } else {
        apiKey = "";  // Key doesn't exist, use empty string
    }
    sendInterval_sec = preferences.getUInt("sendInterval", 30);
    // If sendInterval is 0 or not set, use default value of 30 seconds and save to NVS
    if (sendInterval_sec == 0) {
        sendInterval_sec = 30;
        if (!preferences.putUInt("sendInterval", sendInterval_sec)) {
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'sendInterval' to NVS\n");
        }
        if (debugEnabled) {
            Serial.print("DEBUG: Using default sendInterval (30 seconds) and saving to NVS: ");
            Serial.println(sendInterval_sec);
        }
    }
    ledEnabled = preferences.getBool("ledEnabled", true);
    // NVS key max length is 15 characters, so use shorter key
    deepSleepTimeout_sec = preferences.getUInt("deep_sleep", deepSleepTimeout_sec);
    // If deepSleepTimeout_sec is 0, disable deep sleep
    if (deepSleepTimeout_sec == 0) {
        DeepSleep = false;
        if (debugEnabled) {
            Serial.println("DEBUG: Deep Sleep disabled (timeout = 0)");
        }
    } else {
        DeepSleep = true;
    }
    
    // Load config fetch interval from NVS
    // NVS key max length is 15 characters, so use shorter key
    configFetchInterval_sec = preferences.getUInt("cfg_fetch_int", configFetchInterval_sec);
    if (debugEnabled) {
        Serial.printf("DEBUG: Config fetch interval loaded from NVS: %u seconds\n", configFetchInterval_sec);
    }
    lastConfigFetchTime = 0; // Will be set after first config fetch
    
    // Fallback to build flags if NVS values are empty
    // This ensures devices can connect to server without manual configuration
    #ifdef DEFAULT_SERVER_URL
    if (serverUrl.length() == 0) {
        serverUrl = String(DEFAULT_SERVER_URL);
        // Write default server URL to NVS so it's available on next startup
        if (!preferences.putString("serverUrl", serverUrl)) {
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'serverUrl' to NVS\n");
        }
        if (debugEnabled) {
            Serial.print("DEBUG: Using build flag DEFAULT_SERVER_URL as fallback and saving to NVS: ");
            Serial.println(serverUrl);
        }
    }
    #endif
    
    #ifdef DEFAULT_API_KEY
    if (apiKey.length() == 0) {
        apiKey = String(DEFAULT_API_KEY);
        // Write default API key to NVS so it's available on next startup
        if (!preferences.putString("apiKey", apiKey)) {
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'apiKey' to NVS\n");
        }
        if (debugEnabled) {
            Serial.print("DEBUG: Using build flag DEFAULT_API_KEY as fallback and saving to NVS: ");
            Serial.println(apiKey);
        }
    }
    #endif
    
    // Validate serverUrl format - remove invalid entries like "http://http:"
    if (serverUrl.length() > 0) {
        // Check for malformed URLs (e.g., "http://http:" or "http://https:")
        if (serverUrl.indexOf("http://http") >= 0 || serverUrl.indexOf("https://http") >= 0 ||
            serverUrl.indexOf("http://https") >= 0 || serverUrl.indexOf("https://https") >= 0) {
            if (debugEnabled) {
                Serial.print("DEBUG: Detected malformed serverUrl: ");
                Serial.println(serverUrl);
                Serial.println("DEBUG: Clearing malformed URL, will use default.");
            }
            preferences.remove("serverUrl");
            serverUrl = "";
            // Apply default if available
            #ifdef DEFAULT_SERVER_URL
            serverUrl = String(DEFAULT_SERVER_URL);
            if (debugEnabled) {
                Serial.print("DEBUG: Using default serverUrl: ");
                Serial.println(serverUrl);
            }
            #endif
        }
    }
    
    testActive = preferences.getBool("testModeEnabled", false);
    // Always load testDistance and testInterval_sec from NVS (even if test mode is not active)
    // This ensures they are always available and initialized
    testDistance = preferences.getFloat("testDistance", 0.01);
    testInterval_sec = preferences.getUInt("testInterval", 5);
    
    // If testDistance was not in NVS (default value used), save it now to prevent NVS error
    // Check if the key exists by trying to read it and comparing with a sentinel value
    // Since getFloat returns default if not found, we check if it's the default and save it
    // This ensures the value is always in NVS, even if it was never set before
    if (!preferences.isKey("testDistance")) {
        if (!preferences.putFloat("testDistance", testDistance)) {
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'testDistance' to NVS\n");
        }
        if (debugEnabled) {
            Serial.printf("DEBUG: Initialized testDistance in NVS: %.2f km\n", testDistance);
        }
    }
    
    // Same for testInterval_sec
    if (!preferences.isKey("testInterval")) {
        if (!preferences.putUInt("testInterval", testInterval_sec)) {
            Serial.print("ERROR: getPreferences() - Failed to write parameter 'testInterval' to NVS\n");
        }
        if (debugEnabled) {
            Serial.printf("DEBUG: Initialized testInterval in NVS: %u s\n", testInterval_sec);
        }
    }
    //preferences.end();
    
    if (debugEnabled) {
      displayNVSConfig();
    }
    
}

/**
 * @brief Resets all distance and pulse counters to zero.
 * 
 * Clears both software counters and hardware PCNT unit. Called when a new RFID tag is detected
 * to start fresh distance tracking for the new user.
 * 
 * @note Hardware interaction: PCNT_UNIT (hardware pulse counter)
 * @note Side effects: Resets global distance variables and hardware counter
 */
void resetDistanceCounters() {
    // Reset all distance and pulse counters to zero
    totalDistance_mm = 0;
    distanceInInterval_mm = 0;
    pulsesAtLastSend = 0;
    lastPulseCount = 0;
    currentPulseCount = 0; // Also reset current counter value
    pcnt_counter_clear(PCNT_UNIT); // Reset hardware counter
    
    // Reset speed calculation variables
    currentSpeed_kmh = 0.0;
    previousPulseTime = 0;
    speedHistoryIndex = 0;
    speedHistoryCount = 0;
    // Clear speed history array
    for (int i = 0; i < SPEED_AVERAGE_COUNT; i++) {
        speedHistory[i] = 0.0;
    }

    if (debugEnabled) {
        Serial.println("DEBUG: Distance values reset to zero due to ID tag change.");
    }
}

// --- Buzzer control functions ---
/**
 * @brief Generates a tone on the buzzer for a specified duration.
 * 
 * Controls the active buzzer by setting BUZZER_PIN HIGH for the duration, then LOW.
 * 
 * @param duration_ms Duration of the tone in milliseconds
 * 
 * @note Hardware interaction: BUZZER_PIN (GPIO output)
 * @note Side effects: Blocks execution for duration_ms milliseconds
 */
void buzzer_tone(int duration_ms) {
    // For active buzzer, HIGH = ON, LOW = OFF
    digitalWrite(BUZZER_PIN, HIGH);
    delay(duration_ms);
    digitalWrite(BUZZER_PIN, LOW);
}

/**
 * @brief Plays startup tone sequence (3 short beeps).
 * 
 * Indicates device restart after power-on. Plays 3 beeps of 100ms each with 100ms pauses.
 * 
 * @note Hardware interaction: BUZZER_PIN
 * @note Side effects: Blocks execution for ~500ms
 */
void play_startup_tone() {
    // 3 x short beep = restart after power on
    buzzer_tone(100); delay(100);
    buzzer_tone(100); delay(100);
    buzzer_tone(100);
}

/**
 * @brief Plays wakeup tone sequence (2 short beeps).
 * 
 * Indicates wakeup from deep sleep. Plays 2 beeps of 150ms each with 150ms pause.
 * 
 * @note Hardware interaction: BUZZER_PIN
 * @note Side effects: Blocks execution for ~450ms
 */
void play_wakeup_tone() {
    // 2 x short beep = wakeup from deep sleep
    buzzer_tone(150); delay(150);
    buzzer_tone(150);
}

/**
 * @brief Plays tag detected tone (1 long beep).
 * 
 * Indicates successful RFID tag detection. Plays 1 beep of 500ms.
 * 
 * @note Hardware interaction: BUZZER_PIN
 * @note Side effects: Blocks execution for 500ms
 */
void play_tag_detected_tone() {
    // 1 x long = ID tag detected
    buzzer_tone(500);
}

#ifdef ENABLE_OLED
/**
 * @brief Displays server communication error on OLED display.
 * 
 * Shows detailed error message when server communication fails (API key, server unreachable, maintenance, etc.)
 * Displays user-friendly error descriptions without technical error codes.
 * 
 * @param errorType Error type string (e.g., "API Key", "Server", "Wartung", "Kein WLAN")
 * @param errorCode HTTP error code or 0 for connection error (not displayed, used only for internal logic)
 * 
 * @note Hardware interaction: OLED display (I2C communication)
 * @note Side effects: Updates OLED display buffer and sends to display, turns off LED
 * @note Only compiled if ENABLE_OLED is defined
 */
void display_ServerError(const char* errorType, int errorCode) {
    // Turn off LED on error
    digitalWrite(LED_PIN, LOW);
    
    display.clearBuffer();
    display.setFont(u8g2_font_7x14_tf);
    
    // First line: "Fehler:"
    textline = "Fehler:";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 12);
    display.print(textline);
    
    // Second and third lines: Detailed error description based on error type
    String errorDescription = "";
    String errorDescription2 = "";
    
    if (strcmp(errorType, "API Key") == 0) {
        errorDescription = "API-Key";
        errorDescription2 = "ungültig";
    } else if (strcmp(errorType, "Server") == 0) {
        if (errorCode > 0) {
            errorDescription = "Server";
            errorDescription2 = "nicht erreichbar";
        } else {
            errorDescription = "Keine";
            errorDescription2 = "Verbindung";
        }
    } else if (strcmp(errorType, "Wartung") == 0) {
        errorDescription = "Server";
        errorDescription2 = "in Wartung";
    } else if (strcmp(errorType, "Kein WLAN") == 0) {
        errorDescription = "Keine";
        errorDescription2 = "WLAN-Verbindung";
    } else {
        // Fallback for unknown error types
        errorDescription = errorType;
        errorDescription2 = "";
    }
    
    // Display first line of error description
    textline = errorDescription.c_str();
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 28);
    display.print(textline);
    
    // Display second line of error description (if available)
    if (errorDescription2.length() > 0) {
        textline = errorDescription2.c_str();
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 44);
        display.print(textline);
    }
    
    display.sendBuffer();
}

#ifdef ENABLE_OLED
/**
 * @brief Displays firmware update message on OLED display.
 * 
 * Shows centered message during firmware update process to inform user not to power off the device.
 * 
 * @note Hardware interaction: OLED display (I2C communication)
 * @note Side effects: Updates OLED display buffer and sends to display
 * @note Only compiled if ENABLE_OLED is defined
 */
void display_FirmwareUpdate() {
    display.clearBuffer();
    display.setFont(u8g2_font_7x14_tf);
    
    // First line: "Firmware update"
    textline = "Firmware update";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 28);
    display.print(textline);
    
    // Second line: "Nicht ausschalten!"
    textline = "Nicht";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 44);
    display.print(textline);
    
    textline = "ausschalten!";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 60);
    display.print(textline);
    
    display.sendBuffer();
}

/**
 * @brief Displays configuration check message on OLED display.
 * 
 * Shows centered message when device configuration is being sent to the system.
 * 
 * @note Hardware interaction: OLED display (I2C communication)
 * @note Side effects: Updates OLED display buffer and sends to display
 * @note Only compiled if ENABLE_OLED is defined
 */
void display_ConfigCheck() {
    display.clearBuffer();
    display.setFont(u8g2_font_7x14_tf);
    
    // First line: "Check"
    textline = "Check";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 20);
    display.print(textline);
    
    // Second line: "Konfiguration"
    textline = "Konfiguration";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 36);
    display.print(textline);
    
    // Third line: "MCC-Station"
    textline = "MCC-Station";
    textWidth = display.getStrWidth(textline);
    display.setCursor((128 - textWidth) / 2, 52);
    display.print(textline);
    
    display.sendBuffer();
}
#endif

/**
 * @brief Displays ID tag name on OLED display.
 * 
 * Shows username or default user name. Only shows "ID Tag erkannt!" if a RFID tag was actually detected.
 * Shows error message if no name was found on server.
 * 
 * @param id_name Username string to display (or "NULL" if not found)
 * @param isRfidDetected True if the current idTag came from RFID detection, false if it's the default user
 * 
 * @note Hardware interaction: OLED display (I2C communication)
 * @note Side effects: Updates OLED display buffer and sends to display
 * @note Only compiled if ENABLE_OLED is defined
 */
void display_IdTag_Name(const char* id_name, bool isRfidDetected, bool queryWasSuccessful) {

        if (debugEnabled) Serial.printf("OLED: Show idTagName: '%s' (RFID detected: %s, query successful: %s)\n", id_name, isRfidDetected ? "yes" : "no", queryWasSuccessful ? "yes" : "no");
        
        display.clearBuffer();
        display.setFont(u8g2_font_7x14_tf);

        // Check if name is NULL or empty (no assignment found on server)
        bool nameNotFound = (strcmp(id_name, "NULL") == 0 || strlen(id_name) == 0);
        
        // Only show error message if:
        // 1. Name is actually NULL/empty (nameNotFound)
        // 2. A query was actually made and was successful (queryWasSuccessful)
        // 3. WiFi is connected (so we could actually query the server)
        // 4. No API key error is active (so the query could succeed)
        // This prevents showing the error when WiFi is not connected, API key is wrong, or query was not attempted
        bool canShowNameError = nameNotFound && queryWasSuccessful && (WiFi.status() == WL_CONNECTED) && !apiKeyErrorActive;

        if (canShowNameError) {
            // Show "Radler nicht gefunden" error message (this is what the server returns for HTTP 404)
            // This is more specific than "Kein Kurzname zugewiesen" and matches the server response
            textline = "Fehler:";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 12);
            display.print(textline);

            textline = "Radler nicht";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 28);
            display.print(textline);

            textline = "gefunden";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 44);
            display.print(textline);

            // Show default tag ID so user knows which tag to report to admin (without "Tag:" prefix)
            textline = idTag.c_str();
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 60);
            display.print(textline);
        } else if (nameNotFound) {
            // Name is NULL but we can't show error (WiFi not connected or API key error)
            // Just show the default user info without error message
            if (isRfidDetected) {
        textline = "Id Tag erkannt!";
        textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 12);
        display.print(textline);

        textline = "Nun strampelt:";
        textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 28);
                display.print(textline);
                
                textline = idTag.c_str();
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 50);
                display.print(textline);
            } else {
                // Default user - just show the tag ID
                textline = "Benutzer:";
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 28);
                display.print(textline);
                
                textline = idTag.c_str();
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 50);
                display.print(textline);
            }
        } else {
            // Only show "ID Tag erkannt!" if RFID tag was actually detected
            if (isRfidDetected) {
                textline = "Id Tag erkannt!";
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 12);
                display.print(textline);

                textline = "Nun strampelt:";
                textWidth = display.getStrWidth(textline);
        display.setCursor((128 - textWidth) / 2, 28);
        display.print(textline);

        textWidth = display.getStrWidth(id_name);
        display.setCursor((128 - textWidth) / 2, 50);
        display.print(id_name);
            } else {
                // Default user - just show the name without "ID Tag erkannt!"
                textline = "Benutzer:";
                textWidth = display.getStrWidth(textline);
                display.setCursor((128 - textWidth) / 2, 28);
                display.print(textline);

                textWidth = display.getStrWidth(id_name);
                display.setCursor((128 - textWidth) / 2, 50);
                display.print(id_name);
            }
        }
        
        display.sendBuffer();
}

/**
 * @brief Displays current cycling data on OLED display.
 * 
 * Shows username, current speed, and total distance traveled in kilometers.
 * 
 * @note Hardware interaction: OLED display (I2C communication)
 * @note Side effects: Updates OLED display buffer and sends to display
 * @note Only compiled if ENABLE_OLED is defined
 */
void display_Data() {

        if (debugEnabled) Serial.printf("OLED: Show cycling data.\n");
        
        // Check for speed timeout - if no pulse for 5 seconds, set speed to 0 and reset history
        unsigned long currentTime = millis();
        if (lastPulseTime > 0 && (currentTime - lastPulseTime) >= SPEED_TIMEOUT_MS) {
            currentSpeed_kmh = 0.0;
            // Reset speed history to avoid old values in average
            speedHistoryIndex = 0;
            speedHistoryCount = 0;
            for (int i = 0; i < SPEED_AVERAGE_COUNT; i++) {
                speedHistory[i] = 0.0;
            }
        }
        
        display.clearBuffer();
        display.setFont(u8g2_font_7x14_tf);

        //display.drawStr(10, 12, "Es strampelt:");
        textline = "Es strampelt:";
        textWidth = display.getStrWidth(textline);
        // X-Koordinate: (Gesamtbreite - Textbreite) / 2
        display.setCursor((128 - textWidth) / 2, 12);
        display.print(textline);

        // Only display username if it's valid (not "NULL" or empty)
        if (username.length() > 0 && username != "NULL") {
        textWidth = display.getStrWidth(username.c_str());
        // X-Koordinate: (Gesamtbreite - Textbreite) / 2
        display.setCursor((128 - textWidth) / 2, 28);
        display.print(username.c_str());
        } else {
            // Show default user tag ID instead
            textline = "Benutzer:";
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 28);
            display.print(textline);
            
            textline = idTag.c_str();
            textWidth = display.getStrWidth(textline);
            display.setCursor((128 - textWidth) / 2, 44);
            display.print(textline);
        }

        // Display speed instead of pulse count
        display.drawStr(0, 44,  "Geschw.:");  // 
        String speedStr = String(currentSpeed_kmh, 1) + " km/h";
        display.drawStr(70, 44, speedStr.c_str());  // 
        display.drawStr(0, 60,  "Distanz:");  //
        display.drawStr(70, 60, String(totalDistance_mm/1000000).c_str() );  // distance in kilometer (mm to km)
        display.sendBuffer();     

}
#endif