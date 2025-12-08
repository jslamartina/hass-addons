"""Unit tests for devices module.

This file has been split into three separate files for better organization:
- test_devices_cync_device.py - CyncDevice tests (646 lines, 41 tests)
- test_devices_cync_group.py - CyncGroup tests (503 lines, 12 tests)
- test_devices_cync_tcp.py - CyncTCPDevice tests (1745 lines, 105 tests)

This reduces the original 2867-line file into more manageable components.

To run all device tests, use:
  pytest tests/unit/test_devices_cync_device.py tests/unit/test_devices_cync_group.py
  pytest tests/unit/test_devices_cync_tcp.py

Or run a specific component:
  pytest tests/unit/test_devices_cync_device.py  # Just CyncDevice tests
  pytest tests/unit/test_devices_cync_group.py   # Just CyncGroup tests
  pytest tests/unit/test_devices_cync_tcp.py    # Just CyncTCPDevice tests
"""
