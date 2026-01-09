# Contributing to MyCyclingCity

Welcome to the MyCyclingCity project! This guide will help you set up your development environment and understand the project structure.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [Environment Configuration](#environment-configuration)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [CI/CD Workflow](#cicd-workflow)
- [Hardware-First Approach](#hardware-first-approach)
- [Development Workflow](#development-workflow)

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.x** (check `mcc-web/requirements.txt` for specific version)
- **PlatformIO Core** (installed via pip: `pip install platformio`)
- **Git**
- **VS Code** or **Cursor IDE** (recommended)
- **ESP32 Hardware** (optional, for hardware testing)

### PlatformIO Installation

PlatformIO is typically installed in the user's home directory. The CLI path is:
```
~/.platformio/penv/bin/pio
```

If PlatformIO is not installed, install it via:
```bash
pip install platformio
```

## Initial Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd mycyclingcity
```

### 2. Set Up Python Virtual Environment

**Important**: Virtual environments are stored locally in your home directory, not in the project folder.

```bash
# Create virtual environment in your home directory
python3 -m venv ~/venv_mcc

# Activate virtual environment
source ~/venv_mcc/bin/activate

# Install Django dependencies
cd mcc-web
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the `mcc-web/` directory. The Django application uses `python-decouple` to load environment variables.

**Required Environment Variables:**

Create `mcc-web/.env` with the following variables (adjust values as needed):

```bash
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Database (SQLite is used by default)
# DATABASE_URL=sqlite:///db.sqlite3

# Optional: Production settings
# SESSION_COOKIE_SECURE=False
# CSRF_COOKIE_SECURE=False
```

**Note**: If no `.env` file exists, Django will use default values from `mcc-web/config/settings.py`. However, you **must** set `SECRET_KEY` for production use.

### 4. Initialize Django Database

```bash
cd mcc-web
python manage.py migrate
python manage.py createsuperuser  # Optional: Create admin user
```

## Environment Configuration

### Django Environment Variables

The Django application (`mcc-web`) uses the following environment variables (loaded from `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `django-insecure-YOUR_SECRET_KEY_HERE` | Django secret key (REQUIRED for production) |
| `DEBUG` | `True` | Enable/disable debug mode |
| `ALLOWED_HOSTS` | `mycyclingcity.net,127.0.0.1` | Comma-separated list of allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | `https://mycyclingcity.net` | Comma-separated list of trusted origins |
| `SESSION_COOKIE_SECURE` | `not DEBUG` | Secure session cookies (HTTPS only) |
| `CSRF_COOKIE_SECURE` | `not DEBUG` | Secure CSRF cookies (HTTPS only) |

### PlatformIO Environment

PlatformIO environments are defined in `mcc-esp32/platformio.ini`:

- `heltec_wifi_lora_32_V3` - Heltec WiFi LoRa 32 V3 board
- `heltec_wifi_lora_32_V2` - Heltec WiFi LoRa 32 V2 board
- `wemos_d1_mini32` - Wemos D1 Mini32 board
- `test_mode` - Test mode (extends V3)
- `native` - Native test environment (no hardware required)

## Running the Application

### Django Development Server

```bash
cd mcc-web
source ~/venv_mcc/bin/activate  # If not already activated
python manage.py runserver
```

The server will be available at `http://127.0.0.1:8000/`

### ESP32 Firmware Development

#### Build Firmware

```bash
cd mcc-esp32

# Build for Wemos D1 Mini32
~/.platformio/penv/bin/pio run -e wemos_d1_mini32

# Build for Heltec V3
~/.platformio/penv/bin/pio run -e heltec_wifi_lora_32_V3

# Build for Heltec V2
~/.platformio/penv/bin/pio run -e heltec_wifi_lora_32_V2
```

#### Upload to Device

```bash
cd mcc-esp32

# Upload to Wemos D1 Mini32
~/.platformio/penv/bin/pio run --target upload -e wemos_d1_mini32

# Upload to Heltec V3
~/.platformio/penv/bin/pio run --target upload -e heltec_wifi_lora_32_V3
```

#### Open Serial Monitor

```bash
cd mcc-esp32
~/.platformio/penv/bin/pio device monitor
```

**Note**: The serial monitor speed is configured in `platformio.ini` (typically 115200 baud).

## Testing

### Django Test Suite

The project uses both Django's built-in test framework and pytest.

#### Run All Tests

```bash
cd mcc-web
source ~/venv_mcc/bin/activate

# Using pytest (recommended)
pytest api/tests/ -v

# Using Django test runner
python manage.py test api.tests --verbosity=2

# Using Makefile
make test
```

#### Run Specific Test Categories

```bash
# Unit tests only
pytest api/tests/ -m unit

# Integration tests only
pytest api/tests/ -m integration

# Mileage calculation tests
pytest api/tests/ -m mileage

# Hierarchy lookup tests
pytest api/tests/ -m hierarchy

# Regression tests
pytest api/tests/ -m regression
```

#### Run Tests with Coverage

```bash
pytest api/tests/ --cov=api --cov-report=html
```

#### Load Test Data

```bash
# Load test data into database
python manage.py load_test_data

# Reset database and load test data
python manage.py load_test_data --reset
```

### ESP32 Unit Tests

ESP32 firmware includes comprehensive unit tests that run without hardware:

```bash
cd mcc-esp32
~/.platformio/penv/bin/pio test -e native
```

The `native` environment uses Unity test framework and mocks all hardware dependencies.

### Test Markers

The Django test suite uses pytest markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.regression` - Regression tests
- `@pytest.mark.mileage` - Mileage calculation tests
- `@pytest.mark.hierarchy` - Hierarchy lookup tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.live` - Live API tests (require running server)

## CI/CD Workflow

The project uses GitHub Actions for automated testing and building.

### ESP32 Firmware CI

**Workflow**: `.github/workflows/mcc-esp32-ci.yml`

The CI workflow automatically:
- Builds all firmware environments (Heltec V3, Heltec V2, Wemos D1 Mini32)
- Runs unit tests using the `native` environment
- Validates code on every push and pull request

**To trigger manually:**
- Push to any branch
- Create a pull request
- The workflow runs automatically

### Running CI Locally

You can simulate the CI workflow locally:

```bash
cd mcc-esp32

# Build all environments
~/.platformio/penv/bin/pio run -e heltec_wifi_lora_32_V3
~/.platformio/penv/bin/pio run -e heltec_wifi_lora_32_V2
~/.platformio/penv/bin/pio run -e wemos_d1_mini32

# Run tests
~/.platformio/penv/bin/pio test -e native
```

## Hardware-First Approach

MyCyclingCity follows a **hardware-first development philosophy**:

### Core Principles

1. **Hardware Compatibility First**: All changes must maintain compatibility with ESP32 hardware
2. **API Compatibility**: Firmware (`mcc-esp32`) and web API (`mcc-web/iot`) must remain synchronized
3. **Test on Real Hardware**: When possible, test changes on actual ESP32 devices
4. **Backward Compatibility**: API changes must consider existing deployed firmware

### Hardware Pin Definitions

**Critical**: Always verify pin assignments match the target hardware board.

Pin definitions are set via build flags in `mcc-esp32/platformio.ini`:

- **Wemos D1 Mini32**: `PulseMeasurePin=4`, `LED_PIN=2`, `BUZZER_PIN=14`
- **Heltec V3**: `PulseMeasurePin=2`, `LED_PIN=35`, `VEXT_PIN=36`, `BUZZER_PIN=14`
- **Heltec V2**: `PulseMeasurePin=13`, `LED_PIN=25`, `VEXT_PIN=36`, `BUZZER_PIN=14`

See `.cursorrules` for complete pin mapping.

### API Compatibility Checklist

Before making API changes:

- [ ] Verify firmware can communicate with web API endpoints
- [ ] Test backward compatibility with existing firmware versions
- [ ] Update API documentation if endpoints change
- [ ] Coordinate changes across `mcc-esp32` and `mcc-web/iot` modules
- [ ] Test on actual hardware when possible

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Follow coding standards (see `.cursorrules`)
- Write tests for new functionality
- Update documentation as needed

### 3. Test Your Changes

```bash
# Django tests
cd mcc-web
pytest api/tests/ -v

# ESP32 tests
cd mcc-esp32
~/.platformio/penv/bin/pio test -e native
```

### 4. Commit and Push

```bash
git add .
git commit -m "Description of changes"
git push origin feature/your-feature-name
```

### 5. Create Pull Request

- CI will automatically run tests
- Ensure all tests pass before requesting review
- Include description of changes and testing performed

## Coding Standards

### Language & Comments

- **Code Comments & Documentation**: MUST be in **English** (as of 2025-12-25)
- **HTML/Web-UI Strings**: MUST remain in **German** - DO NOT translate
- **Code Logic**: English variable names, English function names, English comments

### Code Style

- **Web**: Use i18n (`{% trans %}`) for user-facing strings
- **Numbers**: Use `format_km_de` for number formatting
- **UI**: State-of-the-art Glassmorphism, Tailwind CSS
- **Hardware**: Maintain API compatibility between `mcc-esp32` and `mcc-web/iot`

## Getting Help

- Check the main [README.md](README.md) for project overview
- Review [mcc-esp32/README.md](mcc-esp32/README.md) for firmware documentation
- Review [mcc-web/README.md](mcc-web/README.md) for web application documentation
- See [mcc-web/docs/](mcc-web/docs/) for API reference and additional docs

## First Steps for New Developers

1. **Clone the repository** and set up your environment (see [Initial Setup](#initial-setup))
2. **Create `.env` file** in `mcc-web/` directory
3. **Run migrations**: `python manage.py migrate`
4. **Start Django server**: `python manage.py runserver`
5. **Build ESP32 firmware**: `cd mcc-esp32 && ~/.platformio/penv/bin/pio run -e wemos_d1_mini32`
6. **Run tests**: `pytest api/tests/` and `~/.platformio/penv/bin/pio test -e native`
7. **Explore the codebase** using Cursor IDE's AI assistance (configured via `.cursorrules`)

The Cursor IDE AI will guide you through your first `pio run` command and help answer questions about the codebase!




