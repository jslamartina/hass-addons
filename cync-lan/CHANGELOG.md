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