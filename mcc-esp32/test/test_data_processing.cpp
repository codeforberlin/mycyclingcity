#include <unity.h>
#include <cmath>
#include <cfloat>

#ifdef UNITY_TEST_MODE
// Mock includes for native testing
#include "mocks/mock_wifi.h"
#include "mocks/mock_httpclient.h"
#include "mocks/mock_mfrc522.h"
#endif

// Test helper functions for distance and speed calculations
// These mirror the logic from main.cpp

/**
 * Calculate distance from pulse count
 * @param pulseCount Number of pulses
 * @param wheelSize_cm Wheel circumference in cm
 * @return Distance in cm
 */
float calculateDistance_cm(int16_t pulseCount, float wheelSize_cm) {
    return (float)pulseCount * wheelSize_cm;
}

/**
 * Calculate speed in km/h from distance and time
 * @param distance_cm Distance in cm
 * @param time_sec Time interval in seconds
 * @return Speed in km/h
 */
float calculateSpeed_kmh(float distance_cm, unsigned int time_sec) {
    if (time_sec == 0) return 0.0;
    return (distance_cm / (float)time_sec) * (3600.0 / 100000.0);
}

/**
 * Convert distance from cm to km
 * @param distance_cm Distance in cm
 * @return Distance in km
 */
float convertCmToKm(float distance_cm) {
    return distance_cm / 100000.0;
}

void test_data_processing() {
    // Test distance calculation
    TEST_ASSERT_EQUAL_FLOAT(0.0, calculateDistance_cm(0, 210.0));
    TEST_ASSERT_EQUAL_FLOAT(210.0, calculateDistance_cm(1, 210.0));
    TEST_ASSERT_EQUAL_FLOAT(420.0, calculateDistance_cm(2, 210.0));
    TEST_ASSERT_EQUAL_FLOAT(1050.0, calculateDistance_cm(5, 210.0));
    TEST_ASSERT_EQUAL_FLOAT(21000.0, calculateDistance_cm(100, 210.0));
    
    // Test with different wheel sizes
    TEST_ASSERT_EQUAL_FLOAT(200.0, calculateDistance_cm(1, 200.0));
    TEST_ASSERT_EQUAL_FLOAT(250.0, calculateDistance_cm(1, 250.0));
    
    // Test speed calculation
    // 210 cm in 1 second = 0.0021 km in 1 second = 7.56 km/h
    float speed1 = calculateSpeed_kmh(210.0, 1);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 7.56, speed1);
    
    // 2100 cm in 30 seconds = 0.021 km in 30 seconds = 2.52 km/h
    float speed2 = calculateSpeed_kmh(2100.0, 30);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 2.52, speed2);
    
    // 10500 cm in 30 seconds = 0.105 km in 30 seconds = 12.6 km/h
    float speed3 = calculateSpeed_kmh(10500.0, 30);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 12.6, speed3);
    
    // Test zero time (should return 0)
    TEST_ASSERT_EQUAL_FLOAT(0.0, calculateSpeed_kmh(100.0, 0));
    
    // Test zero distance
    TEST_ASSERT_EQUAL_FLOAT(0.0, calculateSpeed_kmh(0.0, 30));
    
    // Test distance conversion cm to km
    TEST_ASSERT_EQUAL_FLOAT(0.0, convertCmToKm(0.0));
    TEST_ASSERT_EQUAL_FLOAT(0.001, convertCmToKm(100.0));
    TEST_ASSERT_EQUAL_FLOAT(0.01, convertCmToKm(1000.0));
    TEST_ASSERT_EQUAL_FLOAT(0.1, convertCmToKm(10000.0));
    TEST_ASSERT_EQUAL_FLOAT(1.0, convertCmToKm(100000.0));
    TEST_ASSERT_EQUAL_FLOAT(10.0, convertCmToKm(1000000.0));
    
    // Test realistic cycling scenario
    // 50 pulses with 210 cm wheel = 10500 cm = 0.105 km
    float distance = calculateDistance_cm(50, 210.0);
    TEST_ASSERT_EQUAL_FLOAT(10500.0, distance);
    
    // In 30 seconds interval
    float speed = calculateSpeed_kmh(distance, 30);
    TEST_ASSERT_FLOAT_WITHIN(0.1, 12.6, speed);
    
    // Convert to km
    float distance_km = convertCmToKm(distance);
    TEST_ASSERT_FLOAT_WITHIN(0.0001, 0.105, distance_km);
}

