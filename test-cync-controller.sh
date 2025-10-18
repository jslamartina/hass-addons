#!/bin/bash
# Test script for cync-controller development
cd "/workspaces/cync-controller" || exit
python -c "from cync_lan.main import main; main()" --enable-export
