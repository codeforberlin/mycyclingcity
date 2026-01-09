#!/bin/bash
# MCC Regression Test Runner with Automated Evaluation

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PATH="/home/roland/venv_mcc"

cd "$PROJECT_DIR"

# Activate virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
else
    echo "Warning: Virtual environment not found at $VENV_PATH"
fi

echo "=========================================="
echo "MCC Regression Test Suite"
echo "=========================================="
echo ""

# Step 1: Load test data
echo "Step 1: Loading test data..."
python manage.py load_test_data --reset 2>&1 | tee /tmp/mcc_test_load.log
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "ERROR: Failed to load test data"
    exit 1
fi
echo "✓ Test data loaded successfully"
echo ""

# Step 2: Run tests
echo "Step 2: Running regression tests..."
TEST_OUTPUT=$(python manage.py test api.tests.test_regression --verbosity=2 2>&1)
TEST_EXIT_CODE=${PIPESTATUS[0]}

echo "$TEST_OUTPUT" | tee /tmp/mcc_test_results.log
echo ""

# Step 3: Evaluate results
echo ""
echo "=========================================="
echo "Automated Test Evaluation"
echo "=========================================="
echo ""

# Run automated evaluation
python "$PROJECT_DIR/api/tests/evaluate_test_results.py" <<< "$TEST_OUTPUT"
EVAL_EXIT_CODE=$?

echo ""
echo "=========================================="
echo "Detailed logs saved to:"
echo "  - Test data load: /tmp/mcc_test_load.log"
echo "  - Test results: /tmp/mcc_test_results.log"
echo "  - Evaluation report: $PROJECT_DIR/api/tests/test_evaluation_report.txt"
echo "  - JSON results: $PROJECT_DIR/api/tests/test_results.json"
echo "=========================================="

# Use evaluation exit code if available, otherwise use test exit code
if [ $EVAL_EXIT_CODE -eq 0 ] && [ $TEST_EXIT_CODE -eq 0 ]; then
    exit 0
else
    exit 1
fi

