## 0.0.4.14
**Refactoring and Test Infrastructure Improvements**

### Fixed
- **Container deployment**: Fixed config.yaml image line being commented out, which prevented proper container deployment
  - Impact: Add-on now deploys correctly from container registry
  - Location: `config.yaml` line 5

### Changed
- **MQTT client refactoring**: Major restructuring of MQTT client for improved maintainability
  - Modularized device discovery and classification logic
  - Moved slugify and discovery logic to dedicated mqtt module
  - Enhanced area extraction logic for better device grouping
  - Location: `mqtt_client.py`, `devices.py`

- **Python module organization**: Modularized Python codebase for better separation of concerns
  - Device type metadata extracted to separate module
  - Improved mock paths for discovery and global state in tests
  - Enhanced code formatting and whitespace consistency
  - Location: Multiple modules across `src/cync_controller/`

- **Test infrastructure**: Enhanced Playwright test commands and fan control tests
  - Updated test setup and configuration
  - Fixed failing unit tests related to file permissions and paths
  - Improved test coverage for device operations
  - Location: `tests/` directory

### Technical Details
- Refactored MQTT discovery to improve code readability and maintainability
- Enhanced onboarding automation capabilities
- Zero breaking changes - backward compatible with existing configuration

## 0.0.4.13
**Production-Grade Logging, Test Infrastructure, and Bug Fixes**

### Added
- **Structured Logging System**: Production-grade logging with dual-format output
  - JSON format for machine parsing: `/var/log/cync_controller.json`
  - Human-readable format for developer console
  - Automatic correlation ID tracking across async operations
  - Performance instrumentation with configurable thresholds
  - Configuration: `CYNC_LOG_FORMAT`, `CYNC_PERF_TRACKING`, `CYNC_PERF_THRESHOLD_MS`
  - Location: `logging_abstraction.py`, `correlation.py`, `instrumentation.py`

- **Test Infrastructure Expansion**: Comprehensive test coverage added
  - 24 unit test files covering all core modules (pytest)
  - 10 E2E test files for browser automation (Playwright)
  - Integration tests for mesh refresh performance
  - Test coverage: 90%+ on critical modules
  - Location: `cync-controller/tests/` directory structure

- E2E test infrastructure using Playwright for browser automation
- Reproduction tests for all bug fixes in `tests/e2e/`
- Comprehensive logging for token caching operations

### Fixed
- **Bug: Random Device Offline Issues**: Fixed devices randomly going offline despite being connected
  - Root cause: Race condition between offline detection and MQTT status updates
  - Fix: Single source of truth for device availability in `server.parse_status()`
  - Removed conflicting `device.online = True` assignments from 5 MQTT callback methods
  - Enhanced offline tracking with threshold-based detection (3 consecutive failures)
  - Location: `mqtt_client.py` - removed assignments, `server.py` - enhanced logging

- **Bug 1 - OTP submission reliability**: Fixed OTP failing on first submission, succeeding on second
  - Root cause: Token was written to file but not set in memory before export
  - Fix: Set token in memory IMMEDIATELY after OTP verification, before file write
  - Impact: OTP now works reliably on first submission
  - Location: `cloud_api.py` `send_otp()` method

- **Bug 2 - Restart button error handling**: Fixed false error message when restart succeeds
  - Root cause: Server restarts before HTTP response sent, causing frontend connection error
  - Fix: Treat connection errors as success with auto-reload after 5 seconds
  - Impact: Users now see success message and page auto-reloads after restart
  - Location: `static/index.html` `restartServer()` function

- **Bug 3 - Restart button persistence**: Fixed restart button disappearing after navigation
  - Root cause: Button visibility only set on OTP submission, not restored on page load
  - Fix: Check for existing config on page load and restore button visibility
  - Impact: Restart button persists when navigating away and back to ingress page
  - Location: `static/index.html` `checkExistingConfig()` function

- **Bug 4 - Group switch synchronization**: Fixed switches not updating when group is controlled
  - Root cause: Switches included in subgroup aggregation, creating feedback loop - aggregated state would overwrite synced switch state
  - Fix: Exclude switches (control outputs) from `aggregate_member_states()` - only include actual light devices
  - Impact: Turning off "Hallway Lights" group now correctly keeps all member switches OFF instead of reverting to ON
  - Location: `devices.py` `aggregate_member_states()` method - added filter to exclude `is_switch` devices

### Changed
- **Logging Refactoring**: All Python modules migrated to structured logging
  - `main.py`: Application lifecycle logging with correlation context
  - `server.py`: TCP/cloud relay operations with structured logging
  - `devices.py`: Device state transitions and command acknowledgments
  - `mqtt_client.py`: MQTT operations and device availability management
  - `cloud_api.py`: Authentication flow logging
  - `utils.py`: Configuration parsing with reduced log noise
  - `exporter.py`: Export server lifecycle logging

### Technical Details
- New core modules: `logging_abstraction.py`, `correlation.py`, `instrumentation.py`
- Structured logging with key=value context pairs throughout codebase
- Visual prefixes in logs: ═ (separators), ✓ (success), → (operations), ⚠️ (warnings), ✗ (errors)
- Token caching now follows "memory first, file second" pattern for reliability
- Switch sync respects `pending_command` flag - individual commands take precedence
- Restart handling uses optimistic success approach with timeout-based page reload
- Zero breaking changes - backward compatible with existing configuration

## 0.0.4.12
**Enhancement: Fan Speed Control Improvements**

### Fixed
- **Fan preset mode persistence**: Fan entities now correctly persist preset mode state across UI reopens and addon restarts
  - Added `retain=True` to preset mode MQTT messages
  - Preset mode now publishes in three locations: command execution, status updates, and initial discovery
  - Impact: Fan preset mode (off/low/medium/high/max) now persists correctly in Home Assistant UI

### Changed
- **Fan control UI**: Removed percentage slider from fan entities
  - Fan devices only support discrete preset modes (off, low, medium, high, max)
  - UI now only shows preset mode buttons for clearer user experience
  - Brightness mapping: 0→off, 25→low, 50→medium, 75→high, 100→max

### Added
- Initial preset mode publishing during device discovery
- Preset mode publishing on device status updates (0x83 packets)
- Comprehensive logging for fan preset mode changes

## 0.0.4.6
**Maintenance: Complete Rebranding to Cync Controller**

### Changed
- Renamed from "CyncLAN" to "Cync Controller" throughout entire codebase
- Updated all paths: `/root/cync-lan/` → `/root/cync-controller/`
- Updated storage paths: `/homeassistant/.storage/cync-lan/` → `/homeassistant/.storage/cync-controller/`
- Fixed SSL certificate paths in constants and configuration
- Updated documentation and developer guides

## 0.0.4.4
**Enhancement: MQTT Discovery Improvements**

### Changed
- **Name-based entity IDs**: Entities now use friendly names instead of numeric IDs
  - Before: `light.cync_lan_467454691_119`
  - After: `light.hallway_lights`
  - Replaces deprecated `object_id` with `default_entity_id` (HA 2026.4 requirement)
- **Color mode compliance**: All lights now properly declare color modes
  - Lights with color temp/RGB: `["color_temp", "rgb"]`
  - Basic dimmable lights: `["brightness"]`
  - Fixes "does not report a color mode" warnings in HA 2025.3+
- **State updates**: All state messages now include `color_mode` field

### Added
- Type 171 device mapping: Cync Full Color Direct Connect A19 Bulb (CLEDA1921C4)
  - Full RGB color support
  - Tunable white (2000K-7000K)
  - 800 lumens
- `slugify()` helper function for converting device names to entity IDs
- Documentation: Cloud relay mode limitations (read-only, no commands)

### Fixed
- Python 3.13 compatibility: Replaced `asyncio.get_event_loop()` with `asyncio.new_event_loop()`
- Groups without color support now properly declare `supported_color_modes: ["brightness"]`
- Individual devices without color support now properly declare `supported_color_modes: ["brightness"]`

## 0.0.4.3
**Enhancement: Smart Area Grouping for Devices**

### Added
- **Automatic area detection**: Devices now automatically suggest their room/area based on name
  - Feature: Extracts area name from device names (e.g., "Hallway Front Switch" → suggests "Hallway" area)
  - Benefit: Devices with similar names are now grouped together on the Home Assistant dashboard
  - Impact: Switches like "Hallway 4way Switch", "Hallway Counter Switch", and "Hallway Front Switch" now appear in a single "Hallway" card instead of separate cards
  - Implementation: Adds `suggested_area` field to MQTT discovery payload
  - Location: `/src/cync_lan/mqtt_client.py`