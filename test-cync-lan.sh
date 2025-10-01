#!/bin/bash
# Test script for cync-lan development
cd "/mnt/supervisor/addons/local/cync-lan"
python -c "from cync_lan.main import main; main()" --enable-export
