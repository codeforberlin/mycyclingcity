/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    Update.h
 * @author  Roland Rutz
 * @note    Mock Update header for native tests
 */

#ifndef Update_h
#define Update_h

#ifdef UNITY_TEST_MODE

#include <cstddef>

// Forward declaration
class Stream;

// Mock Update class for native tests (OTA updates)
class UpdateClass {
public:
    bool begin(size_t size, int command = 0, int ledPin = -1, uint8_t ledOn = HIGH) {
        mock_size = size;
        mock_command = command;
        mock_begin_called = true;
        return true;
    }
    
    size_t write(uint8_t* data, size_t len) {
        mock_written += len;
        return len;
    }
    
    bool end(bool evenIfRemaining = false) {
        mock_end_called = true;
        return true;
    }
    
    void abort() {
        mock_aborted = true;
    }
    
    size_t size() const {
        return mock_size;
    }
    
    size_t progress() const {
        return mock_written;
    }
    
    size_t remaining() const {
        return mock_size > mock_written ? mock_size - mock_written : 0;
    }
    
    bool isFinished() const {
        return mock_end_called;
    }
    
    bool hasError() const {
        return mock_has_error;
    }
    
    void printError(Stream& stream) {
        // Mock implementation
    }
    
    // Mock control functions
    void reset() {
        mock_size = 0;
        mock_written = 0;
        mock_command = 0;
        mock_begin_called = false;
        mock_end_called = false;
        mock_aborted = false;
        mock_has_error = false;
    }
    
    void setError(bool hasError) {
        mock_has_error = hasError;
    }

private:
    size_t mock_size;
    size_t mock_written;
    int mock_command;
    bool mock_begin_called;
    bool mock_end_called;
    bool mock_aborted;
    bool mock_has_error;
};

// Global instance (matching ESP32 API)
extern UpdateClass Update;

#endif // UNITY_TEST_MODE

#endif // Update_h
