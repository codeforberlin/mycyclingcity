/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    test_config.h
 * @author  Roland Rutz
 */

#ifndef TEST_CONFIG_H
#define TEST_CONFIG_H

#include <Arduino.h>

// --- TEST MODE CONFIGURATION ---
// Set these values for testing when the mode is enabled.
// These values can be overridden by build flags in platformio.ini.

// Server URL: Use build flag if defined, otherwise fallback
#ifdef DEFAULT_SERVER_URL
  #define FORCE_SERVER_URL_STR DEFAULT_SERVER_URL
#else
  #define FORCE_SERVER_URL_STR "https://mycyclingcity.de"
#endif

// API Key: Use build flag if defined, otherwise fallback
#ifdef DEFAULT_API_KEY
  #define FORCE_AUTH_TOKEN_STR DEFAULT_API_KEY
#else
  #define FORCE_AUTH_TOKEN_STR "bWNjbGFuZ3JwMDE6ZGhmemc1NEdUUjA3NjVoaA==" // Base64 encoded
#endif

const String FORCE_WIFI_SSID = "akiot01.berlin.freifunk.net";
const String FORCE_WIFI_PASSWORD = "";
const String FORCE_SERVER_URL = FORCE_SERVER_URL_STR;
const String FORCE_AUTH_TOKEN = FORCE_AUTH_TOKEN_STR;
const String FORCE_DEVICE_NAME = "mcc-fez-02";
const String FORCE_ID_TAG = "mccfezuser02";

// Test mode variables
const float FORCE_TEST_DISTANCE = 5.0; // Simulated distance in km
const unsigned int FORCE_TEST_INTERVAL = 5; // Send interval in seconds

#endif
