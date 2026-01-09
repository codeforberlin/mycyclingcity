# Test Suite for mcc-esp32

This test suite uses the Unity Test Framework, which is included by default in PlatformIO.

## Test Structure

```
test/
├── test_main.cpp              # Unity Test Runner - Main entry point
├── test_data_processing.cpp  # Tests for distance and speed calculations
├── test_json_generation.cpp  # Tests for JSON creation and parsing
├── test_rfid_utils.cpp       # Tests for RFID helper functions
├── test_config_utils.cpp     # Tests for configuration utilities
└── mocks/
    ├── mock_wifi.h/.cpp      # Mock for WiFi functionality
    ├── mock_httpclient.h     # Mock for HTTPClient
    └── mock_mfrc522.h        # Mock for MFRC522 RFID reader
```

## Test Environments

### Native Tests (No Hardware Required)

For local tests without ESP32 hardware:

```bash
pio test -e native
```

This environment:
- Runs on the host computer (Linux/Mac/Windows)
- Uses mocks for hardware dependencies
- Ideal for CI/CD pipelines
- Fast execution without hardware requirements

**Use Case**: Test pure logic functions, calculations, JSON generation, and data processing without hardware dependencies.

### ESP32 Tests (Hardware Required)

For tests on the wemos_d1_mini32 board:

```bash
pio test -e wemos_d1_mini32_test
```

This environment:
- Runs on the actual ESP32 board
- Can test hardware functions (with limitations)
- Requires connected hardware

**Use Case**: Integration testing with actual hardware, testing hardware-specific features.

## Running Tests Locally

### All Tests

```bash
# Native tests (recommended for development)
pio test -e native

# ESP32 tests (for hardware integration)
pio test -e wemos_d1_mini32_test
```

### Verbose Output

For detailed test output:

```bash
pio test -e native -v
```

### Individual Test Files

Tests are organized in separate files:
- `test_data_processing.cpp` - Calculation logic
- `test_json_generation.cpp` - JSON processing
- `test_rfid_utils.cpp` - RFID utilities
- `test_config_utils.cpp` - Configuration checks

## Tested Functions

### 1. Data Processing (`test_data_processing.cpp`)
- Distance calculation from pulses (cm)
- Speed calculation (km/h)
- Conversion cm → km
- Realistic cycling scenarios

**Example Test Cases**:
- Zero pulses → zero distance
- Single pulse with 210 cm wheel → 210 cm distance
- Speed calculation from distance and time interval
- Edge cases (zero time, zero distance)

### 2. JSON Generation (`test_json_generation.cpp`)
- Update-Data JSON creation
- Get-User-ID JSON creation
- JSON parsing for server responses
- Error handling for invalid JSON

**Example Test Cases**:
- Valid JSON payload generation
- JSON structure validation
- Parsing valid server responses
- Handling malformed JSON (returns "FEHLER")
- Handling missing fields (returns "NULL")

### 3. RFID Utilities (`test_rfid_utils.cpp`)
- UID to hex string conversion
- Various UID formats (4-byte, 7-byte)
- Edge cases (empty UIDs, null bytes)

**Example Test Cases**:
- 4-byte UID conversion: `[0x12, 0x34, 0x56, 0x78]` → `"12345678"`
- 7-byte UID conversion (MIFARE format)
- Zero-padding for bytes < 0x10
- Maximum value handling (0xFF bytes)

### 4. Configuration Utilities (`test_config_utils.cpp`)
- Critical configuration validation
- Device ID formatting
- URL building (with/without trailing slash)

**Example Test Cases**:
- Missing WiFi SSID detection
- Missing server URL detection
- Zero wheel size detection
- Device ID suffix appending
- URL normalization (removing trailing slashes)

## Mocking Strategy

Tests use conditional compilation with `UNITY_TEST_MODE`:

- **WiFi Mock**: Simulates WiFi connection status
  - `WiFi.status()` returns configurable status
  - `WiFi.begin()` can be verified for correct SSID/password
  - Connection state can be controlled for testing

- **HTTPClient Mock**: Simulates HTTP requests/responses
  - Configurable response codes
  - Request payload verification
  - Header validation
  - Response body simulation

- **MFRC522 Mock**: Simulates RFID reader behavior
  - Card presence simulation
  - UID configuration
  - Read success/failure scenarios

Mocks enable testing logic functions without hardware dependencies, making tests:
- **Fast**: No hardware initialization overhead
- **Reliable**: No dependency on physical connections
- **CI/CD Compatible**: Can run in automated pipelines

## Differences: Native vs. Embedded Tests

### Native Tests (`native` environment)
- **Platform**: Host computer (native)
- **Hardware**: None required
- **Speed**: Very fast (milliseconds)
- **Scope**: Pure logic, calculations, data structures
- **Mocks**: Full hardware mocking
- **Use Case**: Development, CI/CD, regression testing

**Limitations**:
- Cannot test actual hardware interactions
- Hardware-specific features (PCNT, deep sleep) are not testable
- WiFi/HTTP require mocks

### Embedded Tests (`wemos_d1_mini32_test` environment)
- **Platform**: ESP32 microcontroller
- **Hardware**: Physical board required
- **Speed**: Slower (seconds, includes upload time)
- **Scope**: Hardware integration, real peripherals
- **Mocks**: Minimal (only for external dependencies)
- **Use Case**: Hardware validation, integration testing

**Limitations**:
- Requires physical hardware connection
- Slower execution
- May be flaky due to hardware state

## GitHub Actions CI/CD Integration

The project includes a GitHub Actions workflow (`.github/workflows/mcc-esp32-ci.yml`) that automatically:

### Build Validation
1. **Builds all environments**: Compiles firmware for all board configurations
   - `heltec_wifi_lora_32_V3`
   - `heltec_wifi_lora_32_V2`
   - `wemos_d1_mini32`
   - `test_mode`
   - `wemos_d1_mini32_test`

2. **Validates compilation**: Ensures code compiles without errors for all targets

### Test Execution
1. **Runs native tests**: Executes `pio test -e native` automatically
   - All unit tests run in CI/CD pipeline
   - No hardware required
   - Fast feedback on code changes

2. **Test result reporting**: Test results are uploaded as artifacts

### Dependency Management
- **Caches PlatformIO libraries**: Speeds up subsequent builds
- **Caches toolchains**: Reduces download time
- **Automatic dependency resolution**: Handles all `lib_deps` from `platformio.ini`

### Workflow Triggers
- **Push to main/develop**: Automatic testing on code changes
- **Pull requests**: Validates contributions before merge
- **Manual trigger**: On-demand execution via `workflow_dispatch`

### CI/CD Benefits
- **Early error detection**: Catches compilation and logic errors before merge
- **Consistent testing**: Same test environment for all contributors
- **Fast feedback**: Native tests complete in seconds
- **Build verification**: Ensures all board configurations remain buildable

## Notes

1. **Hardware-dependent functions**: Functions like `connectToWiFi()`, `sendDataToServer()` with full hardware integration can only be tested on ESP32. Tests focus on testable logic (calculations, JSON generation, data structures).

2. **ArduinoJson**: JSON tests use a simplified JSON builder for native tests (without ArduinoJson dependency) to avoid Arduino.h requirements. ESP32 tests use full ArduinoJson.

3. **Unity Framework**: PlatformIO integrates Unity automatically. No additional installation required.

4. **Test Coverage**: Current tests focus on pure logic functions. Hardware integration tests require physical devices and are not included in CI/CD pipeline.

## Extending the Test Suite

To add new tests:

1. Create a new test file `test_*.cpp`
2. Implement test functions using `TEST_ASSERT_*` macros
3. Add the function to `test_main.cpp`:
   ```cpp
   extern void test_your_new_tests();
   RUN_TEST(test_your_new_tests);
   ```

### Example Test Function

```cpp
void test_your_new_tests() {
    // Test setup
    int result = your_function(42);
    
    // Assertions
    TEST_ASSERT_EQUAL_INT(84, result);
    TEST_ASSERT_TRUE(condition);
    TEST_ASSERT_FLOAT_WITHIN(0.01, expected, actual);
}
```

## Example Test Output

```
test/test_main.cpp:37:test_data_processing    [PASSED]
test/test_main.cpp:38:test_json_generation    [PASSED]
test/test_main.cpp:39:test_rfid_utils         [PASSED]
test/test_main.cpp:40:test_config_utils       [PASSED]

-----------------------
4 Tests 0 Failures 0 Ignored
OK
```

## Best Practices

1. **Test Pure Logic**: Focus on functions that don't require hardware
2. **Use Mocks**: Mock hardware dependencies for native tests
3. **Test Edge Cases**: Include boundary conditions and error scenarios
4. **Keep Tests Fast**: Native tests should complete in seconds
5. **Document Test Purpose**: Add comments explaining what each test validates
6. **Maintain Test Independence**: Each test should be able to run in isolation

## Troubleshooting

### Tests Fail to Compile
- Verify `UNITY_TEST_MODE` is defined in build flags
- Check that mock implementations are included
- Ensure all required headers are included

### Tests Pass Locally but Fail in CI/CD
- Check for platform-specific code paths
- Verify all dependencies are in `platformio.ini`
- Ensure test environment matches CI/CD setup

### Mock Functions Not Working
- Verify mocks are included before source code
- Check that `UNITY_TEST_MODE` is set correctly
- Ensure mock implementations are in the build path
