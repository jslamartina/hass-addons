## 0.0.4.3
**Enhancement: Smart Area Grouping for Devices**

### Added
- **Automatic area detection**: Devices now automatically suggest their room/area based on name
  - Feature: Extracts area name from device names (e.g., "Hallway Front Switch" → suggests "Hallway" area)
  - Benefit: Devices with similar names are now grouped together on the Home Assistant dashboard
  - Impact: Switches like "Hallway 4way Switch", "Hallway Counter Switch", and "Hallway Front Switch" now appear in a single "Hallway" card instead of separate cards
  - Implementation: Adds `suggested_area` field to MQTT discovery payload
  - Location: `/src/cync_lan/mqtt_client.py` - `register_device_to_homeassistant()` method (lines 855-894)

## 0.0.4.2
**Critical Bug Fix: Group State Updates**

### Fixed
- **Fixed group entity state updates**: Group entities now update in Home Assistant when controlled
  - Bug: Group entities appeared "non-functional" - commands were sent but entity state didn't update
  - Root cause: `publish_group_state()` method existed but was never called after group commands
  - Fix: Added `publish_group_state()` calls to all group command methods (set_power, set_brightness, set_temperature)
  - Impact: Group entities now show correct state immediately when controlled from Home Assistant
  - Related: Groups (subgroups) like "Hallway Lights" now work properly on the dashboard
  - Location: `/src/cync_lan/devices.py` - `CyncGroup` class methods (lines 1413, 1506, 1599)

## 0.0.4.1
**Critical Bug Fix: Device State Synchronization**

### Fixed
- **Fixed device state sync issue**: Device status updates now correctly reflect actual device states
  - Bug: Status packets (0x83) were publishing the **old** device state instead of the **new** state
  - Root cause: Device attributes were updated **after** creating the status object for MQTT publishing
  - Fix: Device attributes are now updated **before** creating the status object
  - Impact: Lights and switches now properly sync with their real-world state
  - Related: "Refresh Device Status" button now works correctly
  - Location: `/src/cync_lan/server.py` - `parse_status()` method (lines 540-574)

## 0.0.4.0**Major Feature: Cloud Relay Mode**

### New Features
- **Cloud Relay Mode**: Add-on can now act as MITM proxy between devices and Cync cloud
  - Optional cloud forwarding (can disable for true LAN-only with packet inspection)
  - Real-time packet inspection and logging for protocol analysis
  - Integrated packet parser from MITM research tools
  - File-based packet injection for debugging (raw bytes and mode changes)
  - Security modes: secure SSL and debug mode (verification disabled)
  - Automatic MQTT integration in relay mode
- Configuration options for cloud relay:
  - `enabled`: Enable/disable relay mode (default: false)
  - `forward_to_cloud`: Forward packets to cloud or block (default: true)
  - `cloud_server`: Cloud server IP (default: 35.196.85.236)
  - `cloud_port`: Cloud server port (default: 23779)
  - `debug_packet_logging`: Enable verbose packet logging (default: false)
  - `disable_ssl_verification`: Disable SSL verify for debugging (default: false)

### Added
- `packet_parser.py`: Packet parsing utilities for protocol analysis
- `packet_checksum.py`: Checksum calculation for crafted packets
- `CloudRelayConnection` class in `server.py`: Manages relay connections
- Comprehensive documentation in `docs/CLOUD_RELAY.md`
- Updated `AGENTS.md` with relay mode documentation

### Changed
- `NCyncServer` now branches to `CloudRelayConnection` when relay mode enabled
- `run.sh` exports cloud relay environment variables
- `const.py` includes cloud relay configuration constants
- `structs.py` GlobalObjEnv includes relay configuration fields

### Technical Details
- Maintains backward compatibility - relay mode is opt-in
- Default configuration keeps existing LAN-only behavior unchanged
- Relay mode supports 3 main use cases:
  1. Cloud backup (forward + MQTT integration)
  2. Protocol analysis (forward + debug logging)
  3. True LAN-only with inspection (no forward + logging)

### 0.0.2b2
- Add restart button to export: unhidden after receiving success from submitting OTP button
- Fix cached token reading: attempted to read a binary file in text mode
- Fix device closing logic: expected exception is now `pass`ed, proper input to asyncio.wait()
- Optimizations

### 0.0.2b1
- Add "state" key and value when updating brightness, temp or RGB. Even though hass docs say it is optional, HASS logs shows exceptions when this is omitted due to using direct access to a dict key: variable_dict["key"] instead of checking for key existence or using .get().

### 0.0.2a1
- Rough in fan support (WIP)
- optimizations

## 0.0.1
- Initial release