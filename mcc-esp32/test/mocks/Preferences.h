/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    Preferences.h
 * @author  Roland Rutz
 * @note    Mock Preferences for native tests
 */

#ifndef Preferences_h
#define Preferences_h

#ifdef UNITY_TEST_MODE

#include <string>
#include <map>

// Mock Preferences class for native tests
class Preferences {
public:
    bool begin(const char* name, bool readOnly = false) {
        mock_namespace = name ? std::string(name) : "";
        mock_read_only = readOnly;
        return true;
    }
    
    void end() {
        // Mock implementation
    }
    
    bool putString(const char* key, const char* value) {
        if (value) {
            mock_data[std::string(key)] = std::string(value);
        }
        return true;
    }
    
    String getString(const char* key, const char* defaultValue = nullptr) {
        auto it = mock_data.find(std::string(key));
        if (it != mock_data.end()) {
            return String(it->second.c_str());
        }
        return defaultValue ? String(defaultValue) : String("");
    }
    
    bool putInt(const char* key, int32_t value) {
        mock_data[std::string(key)] = std::to_string(value);
        return true;
    }
    
    int32_t getInt(const char* key, int32_t defaultValue = 0) {
        auto it = mock_data.find(std::string(key));
        if (it != mock_data.end()) {
            return std::stoi(it->second);
        }
        return defaultValue;
    }
    
    bool putFloat(const char* key, float value) {
        mock_data[std::string(key)] = std::to_string(value);
        return true;
    }
    
    float getFloat(const char* key, float defaultValue = 0.0f) {
        auto it = mock_data.find(std::string(key));
        if (it != mock_data.end()) {
            return std::stof(it->second);
        }
        return defaultValue;
    }
    
    bool putBool(const char* key, bool value) {
        mock_data[std::string(key)] = value ? "1" : "0";
        return true;
    }
    
    bool getBool(const char* key, bool defaultValue = false) {
        auto it = mock_data.find(std::string(key));
        if (it != mock_data.end()) {
            return it->second == "1" || it->second == "true";
        }
        return defaultValue;
    }
    
    bool remove(const char* key) {
        mock_data.erase(std::string(key));
        return true;
    }
    
    void clear() {
        mock_data.clear();
    }
    
    // Mock control functions
    void reset() {
        mock_namespace = "";
        mock_read_only = false;
        mock_data.clear();
    }
    
    std::map<std::string, std::string> getData() const {
        return mock_data;
    }

private:
    std::string mock_namespace;
    bool mock_read_only;
    std::map<std::string, std::string> mock_data;
};

// Global instance (matching ESP32 API)
extern Preferences preferences;

#endif // UNITY_TEST_MODE

#endif // Preferences_h
