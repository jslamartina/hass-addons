#!/bin/bash
set -e

# ========================================================================
# CyncLAN Add-on Rebuild Script
# ========================================================================
# Rebuilds the CyncLAN Home Assistant add-on with the latest source code
# changes from this directory.
# ========================================================================

echo "Rebuilding addon..."
ha addons rebuild local_cync-lan

echo "Restarting addon..."
ha addons restart local_cync-lan

ha addons info local_cync-lan

echo "✓ Addon rebuilt and restarted successfully!"
