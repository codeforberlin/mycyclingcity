/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    mock_arduino.h
 * @author  Roland Rutz
 */

#ifndef MOCK_ARDUINO_H
#define MOCK_ARDUINO_H

#ifdef UNITY_TEST_MODE

#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>

// Arduino compatibility types
typedef uint8_t byte;
typedef bool boolean;

// Minimal Arduino compatibility (not all features needed for simplified tests)

// Arduino compatibility constants
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2

// Arduino compatibility functions
#define delay(ms) /* mocked - no delay in tests */
#define delayMicroseconds(us) /* mocked - no delay in tests */

// Serial mock (minimal implementation)
class SerialClass {
public:
    void begin(unsigned long baud) {}
    void print(const char* str) {}
    void print(int val) {}
    void print(unsigned int val) {}
    void print(long val) {}
    void print(unsigned long val) {}
    void print(float val) {}
    void print(double val) {}
    void println() {}
    void println(const char* str) {}
    void println(int val) {}
    void println(unsigned int val) {}
    void println(long val) {}
    void println(unsigned long val) {}
    void println(float val) {}
    void println(double val) {}
    void printf(const char* format, ...) {}
};

extern SerialClass Serial;

// millis() mock
unsigned long millis();

// pinMode, digitalWrite, digitalRead mocks
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
int digitalRead(uint8_t pin);

// String class mock (minimal)
class String {
public:
    String() : data("") {}
    String(const char* str) : data(str ? str : "") {}
    String(const String& other) : data(other.data) {}
    
    String& operator=(const char* str) {
        data = str ? str : "";
        return *this;
    }
    
    String& operator=(const String& other) {
        data = other.data;
        return *this;
    }
    
    String operator+(const String& other) const {
        return String((data + other.data).c_str());
    }
    
    String operator+(const char* str) const {
        return String((data + (str ? str : "")).c_str());
    }
    
    bool operator==(const String& other) const {
        return data == other.data;
    }
    
    bool operator!=(const String& other) const {
        return data != other.data;
    }
    
    int length() const {
        return data.length();
    }
    
    const char* c_str() const {
        return data.c_str();
    }
    
    bool endsWith(const char* suffix) const {
        size_t suffixLen = strlen(suffix);
        if (suffixLen > data.length()) return false;
        return data.substr(data.length() - suffixLen) == suffix;
    }
    
    void remove(int index) {
        if (index >= 0 && index < (int)data.length()) {
            data.erase(index);
        }
    }
    
    char charAt(int index) const {
        if (index >= 0 && index < (int)data.length()) {
            return data[index];
        }
        return 0;
    }
    
    char& operator[](int index) {
        return data[index];
    }
    
    const char& operator[](int index) const {
        return data[index];
    }

private:
    std::string data;
};

// Arduino.h compatibility
#define ARDUINO 10808

#endif // UNITY_TEST_MODE

#endif // MOCK_ARDUINO_H

