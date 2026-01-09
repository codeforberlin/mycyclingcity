#include <unity.h>

#ifdef UNITY_TEST_MODE
#include <string>
#include <map>
#endif

/**
 * Test helper: Check if critical configuration is missing
 * This mirrors the logic from setup() in main.cpp
 */
bool isCriticalConfigMissing(
    const std::string& wifi_ssid,
    const std::string& idTag,
    float wheel_size,
    const std::string& serverUrl,
    const std::string& authToken,
    unsigned int sendInterval_sec
) {
    return (
        wifi_ssid.length() == 0 ||
        idTag.length() == 0 ||
        wheel_size == 0.0 ||
        serverUrl.length() == 0 ||
        authToken.length() == 0 ||
        sendInterval_sec == 0
    );
}

/**
 * Test helper: Format device ID with suffix
 * This mirrors the logic from sendDataToServer() in main.cpp
 */
std::string formatDeviceId(const std::string& deviceName, const std::string& suffix) {
    std::string finalDeviceId = deviceName;
    if (finalDeviceId.length() > 0) {
        finalDeviceId += suffix;
    }
    return finalDeviceId;
}

/**
 * Test helper: Build final URL from base URL and path
 * This mirrors the logic from sendDataToServer() and getUserIdFromTag() in main.cpp
 */
std::string buildFinalUrl(const std::string& baseUrl, const std::string& path) {
    std::string finalUrl = baseUrl;
    
    // Remove trailing slash if present
    if (finalUrl.length() > 0 && finalUrl.back() == '/') {
        finalUrl.pop_back();
    }
    
    finalUrl += path;
    return finalUrl;
}

void test_config_utils() {
    // Test critical config check - all present
    TEST_ASSERT_FALSE(isCriticalConfigMissing(
        "MyWiFi",
        "a1b2c3d4",
        210.0,
        "https://mycyclingcity.de",
        "api-key-123",
        30
    ));
    
    // Test critical config check - missing WiFi SSID
    TEST_ASSERT_TRUE(isCriticalConfigMissing(
        "",
        "a1b2c3d4",
        210.0,
        "https://mycyclingcity.de",
        "api-key-123",
        30
    ));
    
    // Test critical config check - missing ID tag
    TEST_ASSERT_TRUE(isCriticalConfigMissing(
        "MyWiFi",
        "",
        210.0,
        "https://mycyclingcity.de",
        "api-key-123",
        30
    ));
    
    // Test critical config check - zero wheel size
    TEST_ASSERT_TRUE(isCriticalConfigMissing(
        "MyWiFi",
        "a1b2c3d4",
        0.0,
        "https://mycyclingcity.de",
        "api-key-123",
        30
    ));
    
    // Test critical config check - missing server URL
    TEST_ASSERT_TRUE(isCriticalConfigMissing(
        "MyWiFi",
        "a1b2c3d4",
        210.0,
        "",
        "api-key-123",
        30
    ));
    
    // Test critical config check - missing auth token
    TEST_ASSERT_TRUE(isCriticalConfigMissing(
        "MyWiFi",
        "a1b2c3d4",
        210.0,
        "https://mycyclingcity.de",
        "",
        30
    ));
    
    // Test critical config check - zero send interval
    TEST_ASSERT_TRUE(isCriticalConfigMissing(
        "MyWiFi",
        "a1b2c3d4",
        210.0,
        "https://mycyclingcity.de",
        "api-key-123",
        0
    ));
    
    // Test device ID formatting
    std::string deviceId1 = formatDeviceId("MCC-Device", "_AB12");
    TEST_ASSERT_EQUAL_STRING("MCC-Device_AB12", deviceId1.c_str());
    
    std::string deviceId2 = formatDeviceId("", "_AB12");
    TEST_ASSERT_EQUAL_STRING("", deviceId2.c_str());
    
    std::string deviceId3 = formatDeviceId("TestDevice", "");
    TEST_ASSERT_EQUAL_STRING("TestDevice", deviceId3.c_str());
    
    // Test URL building - no trailing slash
    std::string url1 = buildFinalUrl("https://mycyclingcity.de", "/api/update-data");
    TEST_ASSERT_EQUAL_STRING("https://mycyclingcity.de/api/update-data", url1.c_str());
    
    // Test URL building - with trailing slash
    std::string url2 = buildFinalUrl("https://mycyclingcity.de/", "/api/update-data");
    TEST_ASSERT_EQUAL_STRING("https://mycyclingcity.de/api/update-data", url2.c_str());
    
    // Test URL building - multiple trailing slashes
    std::string url3 = buildFinalUrl("https://mycyclingcity.de//", "/api/update-data");
    TEST_ASSERT_EQUAL_STRING("https://mycyclingcity.de//api/update-data", url3.c_str());
    
    // Test URL building - empty base URL
    std::string url4 = buildFinalUrl("", "/api/update-data");
    TEST_ASSERT_EQUAL_STRING("/api/update-data", url4.c_str());
    
    // Test URL building - get-user-id path
    std::string url5 = buildFinalUrl("https://mycyclingcity.de", "/api/get-user-id");
    TEST_ASSERT_EQUAL_STRING("https://mycyclingcity.de/api/get-user-id", url5.c_str());
}

