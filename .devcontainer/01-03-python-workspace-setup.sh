#!/bin/bash
set -e

echo "Setting up development workspace..."

# Get the workspace parent directory
WORKSPACE_PARENT="$(dirname "${WORKSPACE_DIRECTORY}")"
CYNC_LAN_DIR="${WORKSPACE_PARENT}/cync-lan"

# Create symlinks for easier development
# Remove existing symlink if it points to the wrong location
if [ -L "${WORKSPACE_DIRECTORY}/cync-lan-source" ]; then
  CURRENT_TARGET=$(readlink "${WORKSPACE_DIRECTORY}/cync-lan-source")
  if [ "$CURRENT_TARGET" != "${CYNC_LAN_DIR}" ]; then
    rm "${WORKSPACE_DIRECTORY}/cync-lan-source"
    echo "Removed outdated symlink (was pointing to $CURRENT_TARGET)"
  fi
fi

# Create symlink if it doesn't exist
if [ ! -L "${WORKSPACE_DIRECTORY}/cync-lan-source" ]; then
  ln -s "${CYNC_LAN_DIR}" "${WORKSPACE_DIRECTORY}/cync-lan-source"
  echo "Created symlink: cync-lan-source -> ${CYNC_LAN_DIR}"
fi

# Set up git hooks for the cync-lan repository if it exists
if [ -d "${CYNC_LAN_DIR}" ]; then
  cd "${CYNC_LAN_DIR}"
  if [ -f ".pre-commit-config.yaml" ]; then
    pre-commit install
    echo "Installed pre-commit hooks for cync-lan"
  fi
fi

# Create a development script for easy testing
cat > "${WORKSPACE_DIRECTORY}/test-cync-lan.sh" << EOF
#!/bin/bash
# Test script for cync-lan development
cd "${CYNC_LAN_DIR}"
python -c "from cync_lan.main import main; main()" --enable-export
EOF

chmod +x "${WORKSPACE_DIRECTORY}/test-cync-lan.sh"

echo "Development workspace setup complete"
