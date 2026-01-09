#ifndef MOCK_HTTPCLIENT_H
#define MOCK_HTTPCLIENT_H

#ifdef UNITY_TEST_MODE

#include <string>
#include <map>
#include <cstring>

// HTTP status codes
#define HTTP_CODE_OK 200
#define HTTP_CODE_BAD_REQUEST 400
#define HTTP_CODE_UNAUTHORIZED 401
#define HTTP_CODE_NOT_FOUND 404
#define HTTP_CODE_INTERNAL_SERVER_ERROR 500

// Mock HTTPClient class
class HTTPClient {
public:
    HTTPClient() : mock_http_code(0), mock_response("") {}
    
    void begin(const std::string& url) {
        mock_url = url;
        mock_begin_called = true;
    }
    
    void addHeader(const std::string& name, const std::string& value) {
        mock_headers[name] = value;
    }
    
    int POST(const std::string& payload) {
        mock_payload = payload;
        mock_post_called = true;
        return mock_http_code;
    }
    
    std::string getString() {
        return mock_response;
    }
    
    std::string errorToString(int code) {
        if (code == -1) return "Connection failed";
        if (code == -2) return "Send failed";
        return "Unknown error";
    }
    
    void end() {
        mock_end_called = true;
    }
    
    // Mock control functions
    void setResponseCode(int code) {
        mock_http_code = code;
    }
    
    void setResponse(const std::string& response) {
        mock_response = response;
    }
    
    void reset() {
        mock_url = "";
        mock_payload = "";
        mock_response = "";
        mock_headers.clear();
        mock_http_code = 0;
        mock_begin_called = false;
        mock_post_called = false;
        mock_end_called = false;
    }
    
    // Getters for test verification
    std::string getURL() const { return mock_url; }
    std::string getPayload() const { return mock_payload; }
    std::map<std::string, std::string> getHeaders() const { return mock_headers; }
    bool wasBeginCalled() const { return mock_begin_called; }
    bool wasPostCalled() const { return mock_post_called; }
    bool wasEndCalled() const { return mock_end_called; }

private:
    std::string mock_url;
    std::string mock_payload;
    std::string mock_response;
    std::map<std::string, std::string> mock_headers;
    int mock_http_code;
    bool mock_begin_called;
    bool mock_post_called;
    bool mock_end_called;
};

#endif // UNITY_TEST_MODE

#endif // MOCK_HTTPCLIENT_H

