#!/bin/bash
set -e

echo "Syncing cync-lan source code..."
rsync -av --delete \
  /mnt/supervisor/addons/local/cync-lan/ \
  /mnt/supervisor/addons/local/hass-addons/cync-lan/.cache-cync-lan-python/ \
  --exclude='.*/' --exclude='__pycache__' --exclude='*.pyc'

echo "Rebuilding addon..."
ha addons rebuild local_cync-lan

echo "Restarting addon..."
ha addons restart local_cync-lan

ha addons info local_cync-lan

echo "✓ Addon rebuilt and restarted successfully!"
