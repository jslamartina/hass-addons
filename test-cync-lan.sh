#!/bin/bash
# Test script for cync-lan development
cd "/workspaces/cync-lan" || exit
python -c "from cync_lan.main import main; main()" --enable-export
