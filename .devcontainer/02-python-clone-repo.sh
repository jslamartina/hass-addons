#!/bin/bash
set -e

echo "Cloning cync-lan repository..."

# Get the workspace parent directory
WORKSPACE_PARENT="$(dirname "${WORKSPACE_DIRECTORY}")"
CYNC_LAN_DIR="${WORKSPACE_PARENT}/cync-lan"

# Check if cync-lan directory already exists
if [ -d "${CYNC_LAN_DIR}" ]; then
    echo "cync-lan directory already exists at ${CYNC_LAN_DIR}, skipping clone"
    exit 0
fi

# Clone the repository
cd "${WORKSPACE_PARENT}"
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

echo "cync-lan repository cloned and dependencies installed at ${CYNC_LAN_DIR}"
