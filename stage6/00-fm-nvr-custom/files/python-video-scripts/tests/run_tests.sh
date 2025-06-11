#!/bin/bash

# Install test requirements
pip install -r requirements-test.txt

# Add parent directory to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(dirname $(pwd))"

# Run tests with coverage
python -m pytest --cov=. --cov-report=term-missing test_*.py
