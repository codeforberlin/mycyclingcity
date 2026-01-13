/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    test_main.cpp
 * @author  Roland Rutz
 */

#include <unity.h>

#ifdef UNITY_TEST_MODE
// Include mocks for native testing
#include "mock_arduino.h"
#include "mock_wifi.h"
#include "mocks/mock_httpclient.h"
#include "mocks/mock_mfrc522.h"
#endif

// Include test files
extern void test_data_processing();
extern void test_json_generation();
extern void test_rfid_utils();
extern void test_config_utils();

void setUp(void) {
    // Set up test environment before each test
    // This runs before every test function
#ifdef UNITY_TEST_MODE
    WiFi.reset();
#endif
}

void tearDown(void) {
    // Clean up after each test
    // This runs after every test function
#ifdef UNITY_TEST_MODE
    WiFi.reset();
#endif
}

int main(int argc, char **argv) {
    UNITY_BEGIN();
    
    // Run test suites
    RUN_TEST(test_data_processing);
    RUN_TEST(test_json_generation);
    RUN_TEST(test_rfid_utils);
    RUN_TEST(test_config_utils);
    
    UNITY_END();
    
    return 0;
}

