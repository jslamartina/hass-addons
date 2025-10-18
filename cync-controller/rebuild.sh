#!/bin/bash
set -e

# ========================================================================
# Cync Controller Add-on Rebuild Script
# ========================================================================
# Rebuilds the Cync Controller Home Assistant add-on with the latest source code
# changes from this directory.
# ========================================================================

echo "Rebuilding addon..."
ha addons rebuild local_cync-controller

echo "Restarting addon..."
ha addons restart local_cync-controller

ha addons info local_cync-controller

echo "✓ Addon rebuilt and restarted successfully!"
