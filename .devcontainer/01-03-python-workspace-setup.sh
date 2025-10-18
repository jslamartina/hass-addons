#!/bin/bash
set -e

echo "Setting up development workspace..."

# Get the workspace parent directory
WORKSPACE_PARENT="$(dirname "${WORKSPACE_DIRECTORY}")"
CYNC_CONTROLLER_DIR="${WORKSPACE_PARENT}/cync-controller"

# Set up git hooks for the cync-controller repository if it exists
if [ -d "${CYNC_CONTROLLER_DIR}" ]; then
  cd "${CYNC_CONTROLLER_DIR}"
  if [ -f ".pre-commit-config.yaml" ]; then
    pre-commit install
    echo "Installed pre-commit hooks for cync-controller"
  fi
fi

# Create a development script for easy testing
cat > "${WORKSPACE_DIRECTORY}/test-cync-controller.sh" << EOF
#!/bin/bash
# Test script for cync-controller development
cd "${CYNC_CONTROLLER_DIR}"
python -c "from cync_lan.main import main; main()" --enable-export
EOF

chmod +x "${WORKSPACE_DIRECTORY}/test-cync-controller.sh"

echo "Development workspace setup complete"
