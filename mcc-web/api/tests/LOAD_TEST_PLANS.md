# Load Test Plans

This document describes the planned load test scenarios for the MCC system.

## Current Test Data

**File**: `test_data.json`
- **Purpose**: Basic regression testing
- **Scale**: 2 schools, 5 classes, 4 players, 3 devices
- **Use Case**: Quick validation of core functionality

## Planned Load Test Scenarios

### Scenario 1: Medium Scale (18 Classes)
**File**: `test_data_medium.json` (to be generated)
- **Schools**: 3
- **Classes per School**: 6 each (total: 18 classes)
- **Students per Class**: 25
- **Total Students**: ~450
- **Devices per Class**: 3
- **Total Devices**: 54
- **Use Case**: Typical production environment

**Generate with**:
```bash
python manage.py generate_large_test_data --scenario medium --output api/tests/test_data_medium.json
```

### Scenario 2: Large Scale (35 Classes)
**File**: `test_data_large.json` (to be generated)
- **Schools**: 5
- **Classes per School**: 7 each (total: 35 classes)
- **Students per Class**: 25
- **Total Students**: ~875
- **Devices per Class**: 3
- **Total Devices**: 105
- **Use Case**: Large district with multiple schools

**Generate with**:
```bash
python manage.py generate_large_test_data --scenario large --output api/tests/test_data_large.json
```

### Scenario 3: Extra Large Scale (60 Classes)
**File**: `test_data_xlarge.json` (to be generated)
- **Schools**: 10
- **Classes per School**: 6 each (total: 60 classes)
- **Students per Class**: 25
- **Total Students**: ~1500
- **Devices per Class**: 3
- **Total Devices**: 180
- **Use Case**: Stress testing, performance benchmarking

**Generate with**:
```bash
python manage.py generate_large_test_data --scenario xlarge --output api/tests/test_data_xlarge.json
```

## Custom Scenarios

You can also generate custom scenarios:

```bash
# Custom: 4 schools with 20 classes total
python manage.py generate_large_test_data \
    --schools 4 \
    --classes 20 \
    --students-per-class 30 \
    --devices-per-class 4 \
    --output api/tests/test_data_custom.json
```

## Test Data Structure

All test data files follow the same structure:
- **groups**: Hierarchical group structure (schools → classes)
- **players**: Students assigned to classes
- **devices**: Devices assigned to classes
- **mileage_updates**: Historical mileage data with timestamps
- **expected_results**: Expected totals (calculated after loading)

## Running Load Tests

1. **Generate test data**:
   ```bash
   python manage.py generate_large_test_data --scenario large --output api/tests/test_data_large.json
   ```

2. **Load test data**:
   ```bash
   python manage.py load_test_data --file api/tests/test_data_large.json --reset
   ```

3. **Run tests**:
   ```bash
   python manage.py test api.tests
   ```

4. **Performance testing**:
   - Use Django's test client for API endpoint testing
   - Monitor database query counts
   - Measure response times
   - Check memory usage

## Performance Benchmarks

Target performance metrics:
- **Leaderboard load time**: < 500ms for 35 classes
- **Admin Report generation**: < 2s for 35 classes
- **Database queries**: < 50 queries per page load
- **Memory usage**: < 500MB for 35 classes

## Notes

- Test data generation creates realistic hierarchical structures
- Mileage updates are distributed across the last 30 days
- All groups, players, and devices are marked as visible
- Parent-child aggregation is automatically calculated

