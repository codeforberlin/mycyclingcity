/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    mock_mfrc522.h
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#ifndef MOCK_MFRC522_H
#define MOCK_MFRC522_H

#ifdef UNITY_TEST_MODE

#include <cstdint>
#include <string>
#include <vector>

// Mock Uid structure
struct Uid {
    uint8_t uidByte[10];
    uint8_t size;
    
    Uid() : size(0) {
        for (int i = 0; i < 10; i++) {
            uidByte[i] = 0;
        }
    }
};

// Mock MFRC522 class
class MFRC522 {
public:
    Uid uid;
    
    MFRC522(uint8_t ssPin, uint8_t rstPin) : mock_ss_pin(ssPin), mock_rst_pin(rstPin) {
        mock_card_present = false;
        mock_read_success = false;
    }
    
    void PCD_Init() {
        mock_initialized = true;
    }
    
    uint8_t PCD_ReadRegister(uint8_t reg) {
        if (reg == 0x37) { // VersionReg
            return 0x92; // Typical MFRC522 version
        }
        return 0x00;
    }
    
    void PCD_WriteRegister(uint8_t reg, uint8_t value) {
        mock_last_write_register = reg;
        mock_last_write_value = value;
    }
    
    bool PICC_IsNewCardPresent() {
        return mock_card_present;
    }
    
    bool PICC_ReadCardSerial() {
        if (mock_card_present) {
            return mock_read_success;
        }
        return false;
    }
    
    void PICC_HaltA() {
        mock_halt_called = true;
    }
    
    // Mock control functions
    void setCardPresent(bool present) {
        mock_card_present = present;
    }
    
    void setReadSuccess(bool success) {
        mock_read_success = success;
    }
    
    void setUID(const uint8_t* bytes, uint8_t size) {
        this->uid.size = size;
        for (uint8_t i = 0; i < size && i < 10; i++) {
            this->uid.uidByte[i] = bytes[i];
        }
    }
    
    void reset() {
        mock_card_present = false;
        mock_read_success = false;
        mock_initialized = false;
        mock_halt_called = false;
        uid.size = 0;
        for (int i = 0; i < 10; i++) {
            uid.uidByte[i] = 0;
        }
    }
    
    // Register constants for compatibility
    static constexpr uint8_t VersionReg = 0x37;
    static constexpr uint8_t ComIrqReg = 0x04;
    
    // Getters
    bool isInitialized() const { return mock_initialized; }
    bool wasHaltCalled() const { return mock_halt_called; }

private:
    uint8_t mock_ss_pin;
    uint8_t mock_rst_pin;
    bool mock_card_present;
    bool mock_read_success;
    bool mock_initialized;
    bool mock_halt_called;
    uint8_t mock_last_write_register;
    uint8_t mock_last_write_value;
};

#endif // UNITY_TEST_MODE

#endif // MOCK_MFRC522_H

