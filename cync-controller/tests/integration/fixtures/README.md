# Integration Test Fixtures

This directory contains test data for integration tests.

## Directory Structure

```
fixtures/
├── devices.yaml        # Device and group configurations
├── packets/            # Binary packet samples
│   ├── control_on.bin  # 0x73 control packet (turn on)
│   ├── control_off.bin # 0x73 control packet (turn off)
│   ├── mesh_info.bin   # 0x83 mesh info packet
│   └── broadcast.bin   # 0x43 broadcast packet
└── README.md           # This file
```

## Device Configurations (devices.yaml)

Test devices and groups for integration testing:

- **Test Light 1** (0x1234) - Living Room smart switch
- **Test Light 2** (0x5678) - Bedroom smart bulb with color temp
- **Test Switch 1** (0x9ABC) - Kitchen simple switch
- **Living Room Lights** (group 0xABCD) - Contains Light 1 & 2
- **All Lights** (group 0xDEF0) - Contains all three devices

## Binary Packets (packets/)

Binary packet files contain raw Cync protocol packets for testing:

- **control_on.bin** - 0x73 packet to turn device on
- **control_off.bin** - 0x73 packet to turn device off
- **mesh_info.bin** - 0x83 mesh info response
- **broadcast.bin** - 0x43 state broadcast

These packets are used to test:
- Packet parsing
- Command handling
- ACK generation
- State updates

## Usage

These fixtures are loaded automatically by `conftest.py` and made available to integration tests via pytest fixtures.

Example:
```python
def test_device_control(test_device_config):
    device_id = test_device_config["device_id"]
    # ... test code
```

