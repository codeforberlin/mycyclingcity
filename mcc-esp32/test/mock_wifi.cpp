#ifdef UNITY_TEST_MODE

#include "mocks/mock_wifi.h"

// Initialize static members
int WiFiClass::mock_wifi_status = WL_DISCONNECTED;
bool WiFiClass::mock_wifi_begin_called = false;
std::string WiFiClass::mock_wifi_ssid = "";
std::string WiFiClass::mock_wifi_password = "";
std::string WiFiClass::mock_wifi_local_ip = "192.168.1.100";

// Global WiFi instance
WiFiClass WiFi;

#endif // UNITY_TEST_MODE

