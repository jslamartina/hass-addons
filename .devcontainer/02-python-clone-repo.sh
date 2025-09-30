#!/bin/bash
set -e

echo "Cloning cync-lan repository..."

# Check if cync-lan directory already exists
if [ -d "/workspaces/cync-lan" ]; then
    echo "cync-lan directory already exists, skipping clone"
    exit 0
fi

# Clone the repository
cd /workspaces
git clone https://github.com/jslamartina/cync-lan.git

# Install Python dependencies for the cync-lan package
cd cync-lan
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# Install the package in development mode
if [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
    pip install -e .
fi

echo "cync-lan repository cloned and dependencies installed"
