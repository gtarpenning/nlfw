.PHONY: format test clean

# Default target
all: format test

# Format code using black
format:
	@echo "Formatting code with black..."
	black .

# Run tests - supports passing specific test cases
test:
	@echo "Running tests..."
	python -m pytest -v $(filter-out $@,$(MAKECMDGOALS))

# Run tests with coverage report
test-coverage:
	@echo "Running tests with coverage..."
	python -m pytest --cov=. --cov-report=term-missing -v

# Clean up python cache files
clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -r {} +
	find . -type d -name "*.egg-info" -exec rm -r {} +

# Show help
help:
	@echo "Available commands:"
	@echo "  make format         - Format code using black"
	@echo "  make test          - Run all tests"
	@echo "  make test <path>   - Run specific test (e.g., make test test_mail.py::test_get_unread_messages)"
	@echo "  make test-coverage - Run tests with coverage report"
	@echo "  make clean         - Clean up python cache files"
	@echo "  make all           - Run format and test"
	@echo "  make help          - Show this help message"

# This allows passing arguments to the test target
%:
	@: 