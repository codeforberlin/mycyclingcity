/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    WebServer.h
 * @author  Roland Rutz
 * @note    Mock WebServer for native tests
 */

#ifndef WebServer_h
#define WebServer_h

#ifdef UNITY_TEST_MODE

#include <string>
#include <functional>
#include <map>

// Mock WebServer class for native tests
class WebServer {
public:
    WebServer(int port) : mock_port(port), mock_begin_called(false) {}
    
    void begin() {
        mock_begin_called = true;
    }
    
    void on(const char* uri, std::function<void()> handler) {
        mock_handlers[std::string(uri)] = handler;
    }
    
    void handleClient() {
        // Mock implementation
    }
    
    void send(int code, const char* contentType, const char* content) {
        mock_response_code = code;
        mock_content_type = contentType ? std::string(contentType) : "";
        mock_content = content ? std::string(content) : "";
    }
    
    void send(int code, const char* contentType, const String& content) {
        send(code, contentType, content.c_str());
    }
    
    void sendHeader(const char* name, const char* value, bool first = false) {
        mock_headers[std::string(name)] = std::string(value);
    }
    
    void sendContent(const char* content) {
        mock_content += content ? std::string(content) : "";
    }
    
    void sendContent(const String& content) {
        sendContent(content.c_str());
    }
    
    // Mock control functions
    bool wasBeginCalled() const { return mock_begin_called; }
    int getResponseCode() const { return mock_response_code; }
    std::string getContentType() const { return mock_content_type; }
    std::string getContent() const { return mock_content; }
    
    void reset() {
        mock_begin_called = false;
        mock_response_code = 0;
        mock_content_type = "";
        mock_content = "";
        mock_headers.clear();
        mock_handlers.clear();
    }

private:
    int mock_port;
    bool mock_begin_called;
    int mock_response_code;
    std::string mock_content_type;
    std::string mock_content;
    std::map<std::string, std::string> mock_headers;
    std::map<std::string, std::function<void()>> mock_handlers;
};

#endif // UNITY_TEST_MODE

#endif // WebServer_h
