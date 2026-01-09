.PHONY: test test-regression test-load-data test-reset help

help:
	@echo "MCC Test Suite Commands:"
	@echo "  make test              - Run all regression tests"
	@echo "  make test-regression   - Run regression tests only"
	@echo "  make test-load-data    - Load test data into database"
	@echo "  make test-reset        - Reset database and load test data"
	@echo "  make test-clean        - Reset database (clears all mileage data)"

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

