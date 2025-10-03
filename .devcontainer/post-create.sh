#!/bin/bash
set -e

echo "========================================="
echo "Starting Post-Create Configuration"
echo "========================================="

# Step 1: Make all devcontainer scripts executable
echo "Making devcontainer scripts executable..."
# shellcheck disable=SC2154
chmod +x "${CONTAINER_WORKSPACE_FOLDER}"/.devcontainer/*.sh
echo "  Done!"

# Step 2: Install tmux (optional)
echo "Installing tmux..."
if apt-get install -y tmux; then
  echo "  tmux installed successfully"
else
  echo "  WARNING: tmux installation failed (non-fatal)"
fi

# Step 3: Setup Prettier
echo "Setting up Prettier..."
bash "${CONTAINER_WORKSPACE_FOLDER}"/.devcontainer/00-setup-prettier.sh
echo "  Prettier setup complete!"

# Step 4: Setup Python environment
echo "Setting up Python environment..."
bash "${CONTAINER_WORKSPACE_FOLDER}"/.devcontainer/01-00-python-setup-all.sh
echo "  Python setup complete!"

echo "========================================="
echo "Post-Create Configuration Complete!"
echo "========================================="
