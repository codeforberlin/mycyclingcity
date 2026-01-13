/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    mock_wifi.h
 * @author  Roland Rutz
 */

#ifndef MOCK_WIFI_H
#define MOCK_WIFI_H

#ifdef UNITY_TEST_MODE

#include <cstdint>
#include <string>

// Mock WiFi status constants
#define WL_CONNECTED 3
#define WL_DISCONNECTED 6

// Mock WiFi class
class WiFiClass {
public:
    int status() {
        return mock_wifi_status;
    }
    
    void begin(const char* ssid, const char* password = nullptr) {
        mock_wifi_begin_called = true;
        mock_wifi_ssid = ssid ? std::string(ssid) : "";
        mock_wifi_password = password ? std::string(password) : "";
    }
    
    std::string localIP() {
        return mock_wifi_local_ip;
    }
    
    // Mock control functions
    static void setStatus(int status) {
        mock_wifi_status = status;
    }
    
    static void setLocalIP(const std::string& ip) {
        mock_wifi_local_ip = ip;
    }
    
    static void reset() {
        mock_wifi_status = WL_DISCONNECTED;
        mock_wifi_begin_called = false;
        mock_wifi_ssid = "";
        mock_wifi_password = "";
        mock_wifi_local_ip = "192.168.1.100";
    }
    
    static bool wasBeginCalled() {
        return mock_wifi_begin_called;
    }
    
    static std::string getSSID() {
        return mock_wifi_ssid;
    }
    
    static std::string getPassword() {
        return mock_wifi_password;
    }

private:
    static int mock_wifi_status;
    static bool mock_wifi_begin_called;
    static std::string mock_wifi_ssid;
    static std::string mock_wifi_password;
    static std::string mock_wifi_local_ip;
};

// Global WiFi instance
extern WiFiClass WiFi;

#endif // UNITY_TEST_MODE

#endif // MOCK_WIFI_H

