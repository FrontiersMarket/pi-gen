#!/bin/bash

# This script sets up a virtual environment for the project and installs the required dependencies.

# Navigate to the project directory
cd "$(dirname "$0")"
cd .. # Assuming the script is in the scripts directory

# Create a virtual environment in the 'venv' directory
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Upgrade pip in the virtual environment
pip install --upgrade pip

# Install required packages
pip install -r requirements.txt

echo "Virtual environment setup complete. To activate the environment in the future, run 'source venv/bin/activate'."
