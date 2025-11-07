# 2025 01 27T01 17 00 Python Refactor Plan Dc3B6E0F.Plan

<!-- dc3b6e0f-8d6f-4295-9a30-3d88e6ccc090 10875788-e4bb-4f0c-8058-154778d65539 -->

## Python Codebase Refactor for Agent Comprehension

## Current State Analysis

### Large Files Requiring Split

- `devices.py` (2,934 lines) - Contains 3 classes: CyncDevice, CyncGroup, CyncTCPDevice
- `mqtt_client.py` (2,544 lines) - Contains MQTTClient + command classes + discovery logic

### Linting Issues (281 errors)

- 15x PLR0912 (too many branches)
- 12x PLR0915 (too many statements)
- 2x TRY401 (verbose exception logging)
- 1x TRY400 (use logging.exception)
- 1x RET501 (explicit return None)
- 1x EM102 (exception message)

## Phase 1: Split `devices.py` into Focused Modules

### Current structure (2,934 lines)

- Lines 46-1138: `CyncDevice` (device state, properties, command methods)
- Lines 1139-1559: `CyncGroup` (group management)
- Lines 1561-2935: `CyncTCPDevice` (TCP connection, packet parsing, async tasks)

### New module structure

```python
cync_controller/
├── devices/
│   ├── __init__.py          # Export all classes
│   ├── base_device.py       # CyncDevice class (~500 lines)
│   ├── device_commands.py   # Command methods extracted from CyncDevice (~300 lines)
│   ├── group.py             # CyncGroup class (~420 lines)
│   ├── tcp_device.py        # CyncTCPDevice class core (~600 lines)
│   ├── tcp_connection.py    # Connection/read/write logic (~400 lines)
│   └── tcp_packet_handler.py # Packet parsing logic (~500 lines)
```

### Benefits

- Each file under 600 lines
- Clear separation: state management vs commands vs networking vs groups
- Easier for agents to understand focused responsibilities

## Phase 3: Split `mqtt_client.py` into Focused Modules

### Current structure (2,544 lines)

- Lines 29-56: `DeviceCommand` base class
- Lines 58-128: `CommandProcessor` singleton
- Lines 130-216: Command subclasses (SetPowerCommand, SetBrightnessCommand, etc.)
- Lines 218-2544: `MQTTClient` (connection, discovery, command routing, state updates)

### New module structure

```text
cync_controller/
├── mqtt/
│   ├── __init__.py           # Export MQTTClient
│   ├── client.py             # MQTTClient connection/lifecycle (~400 lines)
│   ├── commands.py           # Command classes + CommandProcessor (~300 lines)
│   ├── discovery.py          # Home Assistant MQTT discovery (~600 lines)
│   ├── command_routing.py    # MQTT message handling/routing (~500 lines)
│   └── state_updates.py      # State publishing to MQTT (~400 lines)
```

### Benefits

- Separates concerns: connection vs discovery vs commands vs routing
- Each module has single responsibility
- Easier to locate specific functionality

## Phase 4: Update Imports Across Codebase

After splitting, update all imports in:

- `server.py` (imports CyncDevice, CyncGroup, CyncTCPDevice, MQTTClient)
- `exporter.py` (imports device classes)
- `main.py` (imports MQTTClient)
- All test files (24 unit tests, 7 E2E tests)

### Strategy

- Maintain backward compatibility by re-exporting from `__init__.py` files
- Example: `from cync_controller.devices import CyncDevice` still works
- Gradually migrate to specific imports: `from cync_controller.devices.base_device import CyncDevice`

## Phase 5: Verification & Testing

### Test coverage verification

- Run full test suite: `npm run test:unit:cov`
- Ensure no coverage regression
- All 24 unit test files must pass
- Rebuild and restart addon: `cd cync-controller && ./rebuild.sh`

### Integration testing

- Deploy to devcontainer Home Assistant
- Verify device discovery works
- Test basic commands (power, brightness)
- Check MQTT message flow
- Monitor logs for errors

## Key Architectural Improvements

### Before (monolithic)

- 2 files containing all device + MQTT logic
- Hard to navigate, find specific functionality
- AI agents struggle with 2,500+ line files

### After (modular)

- 11 focused files, each <600 lines
- Clear separation of concerns
- Each module has single responsibility
- Easier for AI agents to reason about specific areas

### Preserved

- All existing functionality intact
- Test coverage maintained
- Backward-compatible imports via `__init__.py`
- No breaking changes to external consumers

## Success Criteria

- [ ] All 281 linting errors fixed
- [ ] No file exceeds 600 lines
- [ ] All tests pass (24 unit + 7 E2E)
- [ ] Test coverage maintained or improved
- [ ] Add-on rebuilds and runs successfully
- [ ] Device discovery and commands work in live environment
- [ ] Imports updated throughout codebase
- [ ] Documentation updated for new structure

### To-dos

- [ ] Fix all 281 linting errors (PLR0912, PLR0915, TRY400, TRY401, RET501, EM102)
- [ ] Split devices.py (2,934 lines) into 6 focused modules under devices/ directory
- [ ] Split mqtt_client.py (2,544 lines) into 5 focused modules under mqtt/ directory
- [ ] Update all imports across codebase (server.py, main.py, exporter.py, tests)
- [ ] Run full test suite and verify all 24 unit + 7 E2E tests pass with no coverage regression
- [ ] Deploy to devcontainer, test device discovery and commands in live environment
