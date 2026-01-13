# MCC Regression Test Suite

This test suite provides automated regression testing for the MCC mileage tracking system.

## Overview

The test suite uses controlled test data from `test_data.json` to ensure consistent, reproducible test scenarios. All tests verify that calculations match expected values and that data is consistent across different views.

## Test Data

### Current Test Data (Basic)

Test data is defined in `test_data.json` and includes:
- **Groups**: Hierarchical group structure (schools, classes)
- **Players**: Players assigned to groups
- **Devices**: Devices assigned to groups
- **Mileage Updates**: Historical mileage data with timestamps
- **Expected Results**: Expected totals for verification

## Running Tests

### Manual Execution

```bash
# Run all tests
python manage.py test api.tests

# Run specific test class
python manage.py test api.tests.test_regression.GroupTotalsTest

# Run specific test
python manage.py test api.tests.test_regression.GroupTotalsTest.test_group_totals_match_expected

# Run with verbose output
python manage.py test api.tests --verbosity=2
```

### Using pytest

```bash
# Install pytest-django if not already installed
pip install pytest-django

# Run all tests
pytest api/tests/

# Run with coverage
pytest --cov=api api/tests/

# Run specific test
pytest api/tests/test_regression.py::GroupTotalsTest::test_group_totals_match_expected
```

## Test Structure

### Test Classes

1. **GroupTotalsTest**: Verifies group distance_total calculations and parent-child aggregation
2. **CyclistTotalsTest**: Verifies cyclist distance_total calculations
3. **LeaderboardTest**: Tests leaderboard view calculations
4. **BadgeCalculationTest**: Tests badge calculations (daily, weekly, monthly, yearly)
5. **AdminReportTest**: Tests Admin Report analytics calculations
6. **FilterTest**: Tests filtering functionality
7. **DataConsistencyTest**: Verifies consistency across different views

## Test Data Files

### Basic Test Data (`test_data.json`)
- **Purpose**: Quick regression testing
- **Scale**: 2 schools, 5 classes, 4 cyclists, 3 devices
- **Use Case**: Core functionality validation

### Load Test Data (Future)
For larger scale testing, see `LOAD_TEST_PLANS.md` for planned scenarios:
- Medium: 18 classes (3 schools)
- Large: 35 classes (5 schools)
- Extra Large: 60 classes (10 schools)

Generate load test data:
```bash
python manage.py generate_large_test_data --scenario medium --output api/tests/test_data_medium.json
```

## Loading Test Data

Before running tests, load test data:

```bash
# Load basic test data (resets database first)
python manage.py load_test_data --reset

# Load test data from custom file
python manage.py load_test_data --file path/to/test_data.json

# Load large-scale test data
python manage.py load_test_data --file api/tests/test_data_large.json --reset
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Regression Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-django
      - name: Run migrations
        run: python manage.py migrate
      - name: Load test data
        run: python manage.py load_test_data --reset
      - name: Run tests
        run: pytest api/tests/ --verbose
```

### GitLab CI Example

```yaml
test:
  stage: test
  script:
    - pip install -r requirements.txt
    - pip install pytest pytest-django
    - python manage.py migrate
    - python manage.py load_test_data --reset
    - pytest api/tests/ --verbose
```

## Adding New Tests

1. Add test data to `test_data.json` if needed
2. Create test methods in appropriate test class or create new test class
3. Use `RegressionTestBase` as base class for tests that need test data
4. Verify expected results match actual calculations

## Expected Results

Expected results are defined in `test_data.json` under `expected_results`. These values should be manually calculated and verified to ensure test correctness.

## Troubleshooting

- **Tests fail with "Group not found"**: Run `python manage.py load_test_data --reset` first
- **Values don't match**: Check that test data in `test_data.json` is correct and manually verify calculations
- **Database locked errors**: Ensure no other processes are accessing the database

