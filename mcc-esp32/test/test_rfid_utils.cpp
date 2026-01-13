/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    test_rfid_utils.cpp
 * @author  Roland Rutz
 */

#include <unity.h>

#ifdef UNITY_TEST_MODE
#include "mocks/mock_mfrc522.h"
#include <cstring>
#include <string>
#include <cstdio>
#include <cstdint>
#endif

/**
 * Test helper: Convert RFID UID byte array to hexadecimal string
 * This mirrors RFID_MFRC522_uidToHexString() from rfid_mfrc522_control.cpp
 */
std::string uidToHexString(uint8_t* buffer, uint8_t bufferSize) {
    std::string str = "";
    for (uint8_t i = 0; i < bufferSize; i++) {
        if (buffer[i] < 0x10) {
            str += "0";
        }
        char hex[3];
        snprintf(hex, sizeof(hex), "%x", buffer[i]);
        str += hex;
    }
    return str;
}

void test_rfid_utils() {
    // Test UID to hex string conversion - 4 byte UID
    uint8_t uid1[] = {0x12, 0x34, 0x56, 0x78};
    std::string hex1 = uidToHexString(uid1, 4);
    TEST_ASSERT_EQUAL_STRING("12345678", hex1.c_str());
    
    // Test UID to hex string conversion - 7 byte UID (typical MIFARE)
    uint8_t uid2[] = {0x04, 0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC};
    std::string hex2 = uidToHexString(uid2, 7);
    TEST_ASSERT_EQUAL_STRING("04123456789abc", hex2.c_str());
    
    // Test with bytes requiring zero padding
    uint8_t uid3[] = {0x01, 0x0A, 0x0F, 0x10};
    std::string hex3 = uidToHexString(uid3, 4);
    TEST_ASSERT_EQUAL_STRING("010a0f10", hex3.c_str());
    
    // Test with all zeros
    uint8_t uid4[] = {0x00, 0x00, 0x00, 0x00};
    std::string hex4 = uidToHexString(uid4, 4);
    TEST_ASSERT_EQUAL_STRING("00000000", hex4.c_str());
    
    // Test with maximum values
    uint8_t uid5[] = {0xFF, 0xFF, 0xFF, 0xFF};
    std::string hex5 = uidToHexString(uid5, 4);
    TEST_ASSERT_EQUAL_STRING("ffffffff", hex5.c_str());
    
    // Test single byte
    uint8_t uid6[] = {0xAB};
    std::string hex6 = uidToHexString(uid6, 1);
    TEST_ASSERT_EQUAL_STRING("ab", hex6.c_str());
    
    // Test empty buffer
    uint8_t uid7[] = {};
    std::string hex7 = uidToHexString(uid7, 0);
    TEST_ASSERT_EQUAL_STRING("", hex7.c_str());
    
    // Test typical RFID tag UID format
    uint8_t uid8[] = {0x04, 0x8A, 0x3C, 0x2B, 0x1D};
    std::string hex8 = uidToHexString(uid8, 5);
    TEST_ASSERT_EQUAL_STRING("048a3c2b1d", hex8.c_str());
}

