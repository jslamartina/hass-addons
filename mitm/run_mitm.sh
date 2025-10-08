#!/bin/bash
# Run the MITM proxy with logging

cd /mnt/supervisor/addons/local/hass-addons/mitm

LOG_FILE="mitm_proxy.log"

echo "Starting MITM proxy with injection capability..."
echo "Logs will be written to: $LOG_FILE"
echo ""
echo "To inject packets, run in another terminal:"
echo "  echo 'smart' > /tmp/mitm_cmd"
echo "  echo 'traditional' > /tmp/mitm_cmd"
echo ""
echo "To view logs in real-time:"
echo "  tail -f $LOG_FILE"
echo ""

# Run the proxy (logs to file, commands via fifo)
python3 mitm_with_injection.py 2>&1 | tee "$LOG_FILE"
