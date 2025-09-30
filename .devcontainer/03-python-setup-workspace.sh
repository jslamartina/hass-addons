#!/bin/bash
set -e

echo "Setting up development workspace..."

# Create symlinks for easier development
if [ ! -L "/workspaces/hass-addons/cync-lan-source" ]; then
    ln -s /workspaces/cync-lan /workspaces/hass-addons/cync-lan-source
    echo "Created symlink: cync-lan-source -> /workspaces/cync-lan"
fi

# Set up git hooks for the cync-lan repository if it exists
if [ -d "/workspaces/cync-lan" ]; then
    cd /workspaces/cync-lan
    if [ -f ".pre-commit-config.yaml" ]; then
        pre-commit install
        echo "Installed pre-commit hooks for cync-lan"
    fi
fi

# Create a development script for easy testing
cat > /workspaces/hass-addons/test-cync-lan.sh << 'EOF'
#!/bin/bash
# Test script for cync-lan development
cd /workspaces/cync-lan
python -c "from cync_lan.main import main; main()" --enable-export
EOF

chmod +x /workspaces/hass-addons/test-cync-lan.sh

echo "Development workspace setup complete"
