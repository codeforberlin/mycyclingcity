/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    mock_arduino.cpp
 * @author  Roland Rutz
 */

#ifdef UNITY_TEST_MODE

#include "mocks/mock_arduino.h"
#include <ctime>
#include <cstring>

// Serial instance
SerialClass Serial;

// Mock millis() - returns time since program start
static unsigned long start_time = 0;

unsigned long millis() {
    if (start_time == 0) {
        start_time = (unsigned long)time(nullptr) * 1000;
    }
    return ((unsigned long)time(nullptr) * 1000) - start_time;
}

// Mock pin functions
static uint8_t pin_states[256] = {0};
static uint8_t pin_modes[256] = {INPUT};

void pinMode(uint8_t pin, uint8_t mode) {
    if (pin < 256) {
        pin_modes[pin] = mode;
    }
}

void digitalWrite(uint8_t pin, uint8_t val) {
    if (pin < 256) {
        pin_states[pin] = val;
    }
}

int digitalRead(uint8_t pin) {
    if (pin < 256) {
        return pin_states[pin];
    }
    return LOW;
}

#endif // UNITY_TEST_MODE
