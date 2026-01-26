.PHONY: test test-regression test-load-data test-reset help version version-clean

help:
	@echo "MCC Test Suite Commands:"
	@echo "  make test              - Run all regression tests"
	@echo "  make test-regression   - Run regression tests only"
	@echo "  make test-load-data    - Load test data into database"
	@echo "  make test-reset        - Reset database and load test data"
	@echo "  make test-clean        - Reset database (clears all mileage data)"
	@echo ""
	@echo "Version Management:"
	@echo "  make version          - Generate version.txt from git"
	@echo "  make version-clean    - Remove version.txt"

test:
	@echo "Running all tests..."
	python manage.py test api.tests --verbosity=2

test-regression:
	@echo "Running regression tests..."
	python manage.py test api.tests.test_regression --verbosity=2

test-load-data:
	@echo "Loading test data..."
	python manage.py load_test_data

test-reset:
	@echo "Resetting database and loading test data..."
	python manage.py load_test_data --reset

test-clean:
	@echo "Resetting database (clears all mileage data)..."
	python manage.py reset_mileage_data --confirm

test-pytest:
	@echo "Running tests with pytest..."
	pytest api/tests/ --verbose

test-coverage:
	@echo "Running tests with coverage..."
	pip install pytest-cov || true
	pytest api/tests/ --cov=api --cov-report=html --cov-report=term

version:
	@echo "Generating version.txt from git..."
	python utils/generate_version.py

version-clean:
	@echo "Removing version.txt..."
	python utils/generate_version.py --clean

compilemessages:
	@echo "Compiling translation messages (project only, excluding venv libraries)..."
	python manage.py compilemessages --locale de --locale encompilemessages-all:
	@echo "Compiling all translation messages (including venv libraries)..."
	python manage.py compilemessages