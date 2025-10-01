#!/bin/bash
set -e

echo "Setting up Python environment for cync-lan development..."

# Add Python bin directory to system PATH permanently
PYTHON_BIN_DIR="/usr/local/python/3.12.11/bin"
if [ -d "$PYTHON_BIN_DIR" ]; then
  # Create a profile.d script for system-wide PATH (sourced by all shells)
  PROFILE_SCRIPT="/etc/profile.d/python-path.sh"
  if [ ! -f "$PROFILE_SCRIPT" ]; then
    echo "export PATH=\"$PYTHON_BIN_DIR:\$PATH\"" | sudo tee "$PROFILE_SCRIPT" > /dev/null
    sudo chmod +x "$PROFILE_SCRIPT"
    echo "Added $PYTHON_BIN_DIR to system PATH via $PROFILE_SCRIPT"
  fi

  # Export for current session
  export PATH="$PYTHON_BIN_DIR:$PATH"
fi

# Install additional Python packages that might be needed for development
pip install --upgrade pip
pip install pytest pytest-asyncio black isort mypy

# Install development tools
pip install pre-commit

echo "Python development environment setup complete"
