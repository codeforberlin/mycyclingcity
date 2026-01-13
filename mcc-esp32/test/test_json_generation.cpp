/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    test_json_generation.cpp
 * @author  Roland Rutz
 */

#include <unity.h>

#ifdef UNITY_TEST_MODE
// For native tests, we test JSON structure logic without ArduinoJson
#include "mocks/mock_wifi.h"
#include "mocks/mock_httpclient.h"
#include <string>
#include <cstring>
#include <cstdio>
#include <sstream>
#include <iomanip>

// Simple JSON builder for testing (without ArduinoJson dependency)
class SimpleJsonBuilder {
public:
    std::string json;
    
    void addString(const std::string& key, const std::string& value) {
        if (!json.empty() && json.back() != '{') json += ",";
        json += "\"" + key + "\":\"" + value + "\"";
    }
    
    void addNumber(const std::string& key, float value) {
        if (!json.empty() && json.back() != '{') json += ",";
        std::ostringstream oss;
        oss << std::fixed << std::setprecision(2) << value;
        json += "\"" + key + "\":" + oss.str();
    }
    
    std::string build() {
        return "{" + json + "}";
    }
    
    void reset() {
        json = "";
    }
};

#else
// For ESP32, include ArduinoJson normally
#include <Arduino.h>
#include <ArduinoJson.h>
#endif

/**
 * Test helper: Generate JSON payload for update-data endpoint
 * This mirrors the logic from sendDataToServer() in main.cpp
 */
#ifdef UNITY_TEST_MODE
std::string generateUpdateDataJSON(float distance_km, const std::string& device_id, const std::string& id_tag) {
    SimpleJsonBuilder builder;
    builder.addNumber("distance", distance_km);
    builder.addString("device_id", device_id);
    builder.addString("id_tag", id_tag);
    return builder.build();
}
#else
std::string generateUpdateDataJSON(float distance_km, const std::string& device_id, const std::string& id_tag) {
    StaticJsonDocument<200> doc;
    char distanceStr[10];
    snprintf(distanceStr, sizeof(distanceStr), "%.2f", distance_km);
    doc["distance"] = distanceStr;
    doc["device_id"] = device_id;
    doc["id_tag"] = id_tag;
    std::string jsonPayload;
    serializeJson(doc, jsonPayload);
    return jsonPayload;
}
#endif

/**
 * Test helper: Generate JSON payload for get-user-id endpoint
 * This mirrors the logic from getUserIdFromTag() in main.cpp
 */
#ifdef UNITY_TEST_MODE
std::string generateGetUserIdJSON(const std::string& tag_id) {
    SimpleJsonBuilder builder;
    builder.addString("id_tag", tag_id);
    return builder.build();
}
#else
std::string generateGetUserIdJSON(const std::string& tag_id) {
    StaticJsonDocument<100> doc;
    doc["id_tag"] = tag_id;
    std::string jsonPayload;
    serializeJson(doc, jsonPayload);
    return jsonPayload;
}
#endif

/**
 * Test helper: Parse JSON response from get-user-id endpoint
 * Simple parser for testing (without ArduinoJson)
 */
#ifdef UNITY_TEST_MODE
std::string parseGetUserIdResponse(const std::string& jsonResponse) {
    // Check for empty response
    if (jsonResponse.empty()) {
        return "FEHLER";
    }
    
    // Check for valid JSON structure (must start with { and end with })
    if (jsonResponse.front() != '{' || jsonResponse.back() != '}') {
        return "FEHLER";
    }
    
    // Simple JSON parsing for test purposes
    size_t user_id_pos = jsonResponse.find("\"user_id\"");
    if (user_id_pos == std::string::npos) {
        return "NULL";
    }
    
    size_t colon_pos = jsonResponse.find(":", user_id_pos);
    if (colon_pos == std::string::npos) {
        return "FEHLER";
    }
    
    size_t value_start = jsonResponse.find("\"", colon_pos);
    if (value_start == std::string::npos) {
        return "FEHLER";
    }
    
    size_t value_end = jsonResponse.find("\"", value_start + 1);
    if (value_end == std::string::npos) {
        return "FEHLER";
    }
    
    return jsonResponse.substr(value_start + 1, value_end - value_start - 1);
}
#else
std::string parseGetUserIdResponse(const std::string& jsonResponse) {
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, jsonResponse);
    if (error) {
        return "FEHLER";
    }
    if (doc.containsKey("user_id")) {
        return doc["user_id"].as<std::string>();
    }
    return "NULL";
}
#endif

void test_json_generation() {
    // Test update-data JSON generation
    std::string json1 = generateUpdateDataJSON(0.105, "MCC-Device_AB12", "a1b2c3d4");
    
    // Verify JSON contains required fields
    TEST_ASSERT_TRUE(json1.find("\"distance\"") != std::string::npos);
    TEST_ASSERT_TRUE(json1.find("\"device_id\"") != std::string::npos);
    TEST_ASSERT_TRUE(json1.find("\"id_tag\"") != std::string::npos);
    TEST_ASSERT_TRUE(json1.find("MCC-Device_AB12") != std::string::npos);
    TEST_ASSERT_TRUE(json1.find("a1b2c3d4") != std::string::npos);
    
    // Test with different values
    std::string json2 = generateUpdateDataJSON(1.5, "MCC-Test_CD34", "12345678");
    TEST_ASSERT_TRUE(json2.find("1.50") != std::string::npos || json2.find("1.5") != std::string::npos);
    TEST_ASSERT_TRUE(json2.find("MCC-Test_CD34") != std::string::npos);
    TEST_ASSERT_TRUE(json2.find("12345678") != std::string::npos);
    
    // Test get-user-id JSON generation
    std::string json3 = generateGetUserIdJSON("a1b2c3d4");
    TEST_ASSERT_TRUE(json3.find("\"id_tag\"") != std::string::npos);
    TEST_ASSERT_TRUE(json3.find("a1b2c3d4") != std::string::npos);
    
    // Test JSON parsing - valid response
    std::string response1 = "{\"user_id\":\"MaxMustermann\"}";
    std::string userId1 = parseGetUserIdResponse(response1);
    TEST_ASSERT_EQUAL_STRING("MaxMustermann", userId1.c_str());
    
    // Test JSON parsing - NULL response
    std::string response2 = "{\"user_id\":\"NULL\"}";
    std::string userId2 = parseGetUserIdResponse(response2);
    TEST_ASSERT_EQUAL_STRING("NULL", userId2.c_str());
    
    // Test JSON parsing - missing user_id field
    std::string response3 = "{\"error\":\"not found\"}";
    std::string userId3 = parseGetUserIdResponse(response3);
    TEST_ASSERT_EQUAL_STRING("NULL", userId3.c_str());
    
    // Test JSON parsing - invalid JSON (missing closing brace)
    std::string response4 = "{\"user_id\":\"test\"";
    std::string userId4 = parseGetUserIdResponse(response4);
    TEST_ASSERT_EQUAL_STRING("FEHLER", userId4.c_str());
    
    // Test JSON parsing - empty response
    std::string response5 = "";
    std::string userId5 = parseGetUserIdResponse(response5);
    TEST_ASSERT_EQUAL_STRING("FEHLER", userId5.c_str());
    
    // Test distance formatting in JSON
    std::string json4 = generateUpdateDataJSON(0.01, "Device", "Tag");
    // Should contain "0.01" or similar
    TEST_ASSERT_TRUE(json4.find("0.01") != std::string::npos || 
                     json4.find("0.010") != std::string::npos ||
                     json4.find("1e-2") != std::string::npos);
    
    // Test with larger distance
    std::string json5 = generateUpdateDataJSON(10.5, "Device", "Tag");
    TEST_ASSERT_TRUE(json5.find("10.5") != std::string::npos || 
                     json5.find("10.50") != std::string::npos);
}

