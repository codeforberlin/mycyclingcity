# MCC-Web Test Suite Documentation

## Overview

This test suite provides comprehensive coverage for the MCC-Web Django application, including:

- **Unit Tests**: Model logic, business rules, and utility functions
- **Integration Tests**: Database interactions, hierarchy lookups, and complex queries
- **View Tests**: API endpoint functionality and error handling
- **Live API Tests**: Integration tests against a running Gunicorn instance

## Test Structure

```
api/tests/
├── conftest.py                    # Shared fixtures and factories
├── test_models.py                # Unit tests for all models
├── test_mileage_calculation.py   # Mileage calculation logic tests
├── test_integration_hierarchy.py # Hierarchy lookup integration tests
├── test_views.py                 # API endpoint view tests
├── test_live_api.py              # Live API tests against Gunicorn
└── test_regression.py            # Existing regression tests
```

## Prerequisites

Install test dependencies:

```bash
pip install -r requirements.txt
```

Required packages:
- `pytest` - Test framework
- `pytest-django` - Django integration for pytest
- `factory-boy` - Test data factories

## Running Tests

### Run All Tests

```bash
pytest api/tests/
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest api/tests/ -m unit

# Integration tests only
pytest api/tests/ -m integration

# Mileage calculation tests
pytest api/tests/ -m mileage

# Hierarchy lookup tests
pytest api/tests/ -m hierarchy

# Live API tests (requires running Gunicorn)
pytest api/tests/ -m live
```

### Run Specific Test Files

```bash
# Test models only
pytest api/tests/test_models.py

# Test mileage calculations only
pytest api/tests/test_mileage_calculation.py

# Test views only
pytest api/tests/test_views.py
```

### Run with Verbose Output

```bash
pytest api/tests/ -v
```

### Run with Coverage

```bash
pytest api/tests/ --cov=api --cov-report=html
```

## Live API Testing

Live API tests run against a running Gunicorn instance. These tests verify:

- HTTP status codes
- JSON structure validity
- German number formatting (comma as decimal separator)
- All API endpoints

### Setup for Live Testing

1. Start Gunicorn server:

```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000
```

2. Run live tests:

```bash
# Use default URL (http://127.0.0.1:8000)
pytest api/tests/test_live_api.py -m live

# Specify custom URL
pytest api/tests/test_live_api.py -m live --base-url=http://localhost:8000

# Specify custom API key
pytest api/tests/test_live_api.py -m live --api-key=YOUR-API-KEY
```

**Note:** After the refactoring, the leaderboard view moved from `/map/kiosk/leaderboard` to `/leaderboard/kiosk/`. The tests have been updated accordingly. Also note that API endpoints use "cyclist" naming (e.g., `/api/get-cyclist-coins/`, `/api/get-cyclist-distance/`), but JSON responses may still use "players" as field names for backward compatibility.

### Environment Variables

You can also set environment variables:

```bash
export TEST_BASE_URL=http://127.0.0.1:8000
export TEST_API_KEY=YOUR-API-KEY
pytest api/tests/test_live_api.py -m live
```

## Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.mileage` - Mileage calculation tests
- `@pytest.mark.hierarchy` - Hierarchy lookup tests
- `@pytest.mark.live` - Live API tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.regression` - Regression tests

## Test Fixtures

### Common Fixtures (in conftest.py)

- `api_key` - API key for authentication
- `admin_user` - Admin user for testing
- `group_hierarchy` - Simple group hierarchy (parent + 2 children)
- `player_with_group` - Player with associated group
- `device_with_group` - Device with associated group
- `active_travel_track` - Active travel track with milestones
- `active_event` - Active event
- `complete_test_scenario` - Complete scenario with all entities
- `today_start` - Start of today (00:00:00)
- `yesterday_start` - Start of yesterday
- `tomorrow_start` - Start of tomorrow

### Factory Classes

All models have corresponding factory classes:

- `UserFactory`
- `GroupFactory`
- `PlayerFactory`
- `DeviceFactory`
- `TravelTrackFactory`
- `EventFactory`
- `MilestoneFactory`
- `GroupTravelStatusFactory`
- `GroupEventStatusFactory`
- `HourlyMetricFactory`
- `PlayerDeviceCurrentMileageFactory`
- `KioskDeviceFactory`
- `KioskPlaylistEntryFactory`

## Test Coverage Areas

### Models (test_models.py)

- Model creation and validation
- Model methods and properties
- Model relationships
- Business logic in models
- Unique constraints

### Mileage Calculation (test_mileage_calculation.py)

- Midnight resets and date boundary handling
- Cumulative sums and session management
- HourlyMetric aggregation
- PlayerDeviceCurrentMileage updates
- Daily/weekly/monthly/yearly calculations

### Hierarchy Lookups (test_integration_hierarchy.py)

- ID Tag -> Group -> Event hierarchy lookups
- Database queries with select_related and prefetch_related
- N+1 query prevention
- Complex relationship traversals
- Multi-level group hierarchies

### API Views (test_views.py)

- All API endpoints
- HTTP status codes
- JSON response structure
- Error handling
- Authentication/Authorization
- Input validation

### Live API (test_live_api.py)

- Server health checks
- All API endpoints against live server (using correct endpoint names: cyclists, not players)
- German number formatting in HTML responses
- JSON response format validation
- Error handling
- Note: Endpoints use "cyclist" naming (e.g., `/api/get-cyclist-coins/`, `/api/get-cyclist-distance/`), but JSON responses may still use "players" as field names for backward compatibility

## Writing New Tests

### Example: Unit Test

```python
@pytest.mark.unit
@pytest.mark.django_db
class TestMyModel:
    def test_my_model_creation(self, group_hierarchy):
        group = group_hierarchy['parent']
        assert group.name == 'Parent Group'
```

### Example: Integration Test

```python
@pytest.mark.integration
@pytest.mark.django_db
class TestMyIntegration:
    def test_complex_query(self, complete_test_scenario):
        scenario = complete_test_scenario
        # Test complex query logic
```

### Example: Live API Test

```python
@pytest.mark.live
class TestMyLiveAPI:
    def test_my_endpoint(self, session, api_key):
        url = f"{session.base_url}/api/my-endpoint"
        response = session.get(url, headers={'X-Api-Key': api_key})
        assert response.status_code == 200
```

## Best Practices

1. **Use Factories**: Always use factory classes instead of creating models directly
2. **Use Fixtures**: Leverage shared fixtures for common test scenarios
3. **Mark Tests**: Use appropriate pytest markers for test organization
4. **Test Edge Cases**: Include tests for error conditions and edge cases
5. **Test Localization**: Verify German number formatting where applicable
6. **Prevent N+1 Queries**: Use select_related and prefetch_related in integration tests
7. **Clean Up**: Tests should clean up after themselves (pytest-django handles this)

## Troubleshooting

### Database Lock Errors

If you encounter database lock errors, ensure:
- Only one test process is running
- Database is properly configured
- No other processes are accessing the test database

### Live API Tests Failing

If live API tests fail:
1. Verify Gunicorn is running: `curl http://127.0.0.1:8000/admin/`
2. Check API key is correct
3. Verify database has test data if needed
4. Check server logs for errors

### Import Errors

If you encounter import errors:
1. Ensure you're in the project root directory
2. Verify virtual environment is activated
3. Check that all dependencies are installed: `pip install -r requirements.txt`

## Continuous Integration

Tests are designed to run in CI/CD pipelines. Example GitHub Actions workflow:

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: pytest api/tests/ -v
```

## Contributing

When adding new features:
1. Write tests first (TDD approach)
2. Ensure all tests pass
3. Maintain or improve test coverage
4. Update this documentation if needed

