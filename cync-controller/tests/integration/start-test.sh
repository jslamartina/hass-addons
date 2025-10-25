#!/bin/sh
# Integration test startup script
# Copies test config from fixtures to writable config directory

set -e

echo "Copying test config from fixtures to config directory..."
cp /data/fixtures/cync_mesh.yaml /data/config/cync_mesh.yaml
echo "Starting cync-controller..."
exec cync-controller
