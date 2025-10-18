# Home Assistant UI Exploration - Agent Findings

**Date:** October 11, 2025
**Access URL:** http://localhost:8123
**Credentials:** Stored in `hass-credentials.env` (dev/dev)

## Overview

Successfully logged into and explored the Home Assistant development instance. The system is running with the CyncLAN Bridge add-on and EMQX MQTT broker integrated.

## System Architecture

### Navigation Structure

The Home Assistant UI features a left sidebar with the following main sections:

1. **Overview** - Main dashboard with device controls
2. **Map** - Location tracking
3. **Energy** - Energy monitoring
4. **Activity** - Recent activity log
5. **History** - Historical data
6. **CyncLAN** - Custom integration for Cync device export
7. **EMQX** - MQTT broker interface
8. **Media** - Media controls
9. **To-do lists** - Task management
10. **Developer tools** - System debugging and testing
11. **Settings** - System configuration

### Current System State

**Notifications:** 1 pending
**Updates Available:** 1 (Home Assistant Core 2025.11.0.dev202510100235)
**System Issues:** 8 (primarily supervisor warnings about Network Manager and Systemd-Resolved)

## CyncLAN Integration

### Add-on Status

- **Version:** 0.0.3.1
- **Status:** Running
- **Hostname:** `local-cync-controller`
- **CPU Usage:** 0%
- **RAM Usage:** 0%

### Add-on Configuration

**Enabled Features:**
- ✓ Start on boot
- ✗ Watchdog (disabled)
- ✓ Add to sidebar
- ✓ Ingress (web UI enabled)

**Badges:**
- Rating: 7
- Host access enabled
- Apparmor enabled
- Ingress enabled

### CyncLAN Components

The add-on provides three main components:

1. **Exporter** - FastAPI server with ingress page for device export from Cync cloud using 2FA (emailed OTP)
   - Supports token caching
   - Web interface accessible via sidebar

2. **nCync** - Async TCP socket server that masquerades as the Cync cloud controller
   - Requires DNS redirection

3. **Comms** - aiomqtt MQTT client for HASS communication using MQTT JSON schema

### Device Export Interface

The CyncLAN sidebar link opens an ingress page (`/local_cync-controller/ingress`) with:
- **Start Export** button - Attempts to use cached tokens first, prompts for OTP if needed
- **OTP Input Field** - For entering the emailed one-time password
- **Submit OTP** button - Submits OTP and caches valid tokens

### Bridge Status Entities

The following binary sensors/buttons are exposed (all currently showing "Unavailable"):
- Cync emailed OTP (number input)
- Restart CyncLAN Bridge (button)
- Start Export (button)
- Submit OTP (button)
- Cync Devices Managed (sensor)
- Cync Export Server Running (sensor)
- Cync MQTT Client Connected (sensor)
- nCync TCP Server Running (sensor)
- TCP Devices Connected (sensor)

## Discovered Devices

### Device Summary

The system currently manages the following Cync devices:

**Fan Devices (1):**
- Master Bedroom Fan Switch (on/off control)

**Light Devices (18):**

#### Hallway (9 lights)
- Hallway 4way Switch *(checked, 33% brightness)*
- Hallway Counter Switch *(checked)*
- Hallway Floodlight 1-6 *(all checked)*
- Hallway Front Switch *(checked)*

#### Kitchen (3 lights - offline/disabled)
- Kitchen Floodlight 1-3 *(all disabled/unavailable)*

#### Living Room (6 lights - off)
- Living Room Floodlight 1-6 *(all unchecked)*
- Living Room Lamp *(disabled/unavailable)*

### Device Control Interface

Clicking on any active light entity opens a modal dialog with:
- Current brightness percentage
- Last update timestamp
- Visual brightness indicator (lightbulb graphic)
- Brightness slider control
- Toggle on/off button
- Additional options: History, Settings, Device Info, Related entities

**Example:** Hallway 4way Switch
- Current state: On at 33% brightness
- Last changed: 9 minutes ago
- Controls: Brightness slider + toggle button

## Developer Tools

### Available Tabs

1. **YAML** - Configuration validation and reload controls
   - Check configuration
   - Restart Home Assistant
   - Reload individual components (automations, scripts, MQTT entities, etc.)

2. **States** - Real-time entity state viewer
   - Shows all entity IDs with current state and attributes
   - Filterable by entity, state, or attributes
   - Notable entities observed:
     - `binary_sensor.cync_lan_bridge_export_server_running` (unavailable)
     - `binary_sensor.cync_lan_bridge_mqtt_client_connected` (unavailable)
     - `binary_sensor.cync_lan_bridge_tcp_server_running` (unavailable)
     - `button.cync_lan_bridge_restart`
     - `button.cync_lan_bridge_start_export`
     - `button.cync_lan_bridge_submit_otp`

3. **Actions** - Service call testing
4. **Template** - Template rendering and testing
5. **Events** - Event monitoring
6. **Statistics** - Statistical data inspection
7. **Assist** - Voice assistant testing

## Settings & Configuration

### Add-ons Dashboard

Two add-ons are currently installed and running:

1. **CyncLAN Bridge** *(running)*
   - Local controller for Cync/C by GE smart devices
   - Requires DNS redirection

2. **EMQX** *(running)*
   - Open-source MQTT broker
   - Alternative to Mosquitto

### Configuration Sections Available

- Home Assistant Cloud
- Devices & services
- Automations & scenes
- Areas, labels & zones
- Add-ons
- Dashboards
- Voice assistants
- Tags
- People
- System (backups, logs, reboot)
- About

## Key Observations

### Integration Status

The CyncLAN Bridge is installed and the add-on container is running, but the internal services (TCP server, MQTT client, export server) are showing as unavailable. This suggests either:
1. The add-on needs to be restarted
2. Configuration is incomplete (MQTT credentials, DNS setup)
3. The services haven't been started yet

### DNS Requirement

A prominent alert on the add-on info page states:
> "DNS redirection is REQUIRED, please see [here](https://github.com/jslamartina/hass-addons/tree/dev/docs/user/dns-setup.md) for documentation and examples"

This is critical for the nCync TCP server to intercept device communications.

### Device States

- Most Hallway lights are ON (checked) with various brightness levels
- Kitchen lights appear offline (disabled switches)
- Living Room lights are mostly OFF
- Some devices show "disabled" status, indicating they may be unavailable or not properly configured

### Architecture Pattern

The CyncLAN integration follows a clean architecture:
1. Devices connect to the local TCP server (thinking they're reaching the cloud)
2. TCP server handles device protocol
3. MQTT client bridges device states to Home Assistant
4. Web exporter provides device configuration from cloud account

## Screenshots Captured

1. `homeassistant-overview.png` - Main overview dashboard
2. `cynclan-export-page.png` - CyncLAN device export interface
3. `settings-dashboard.png` - Settings main page
4. `addons-dashboard.png` - Add-ons list
5. `cynclan-addon-info.png` - CyncLAN Bridge detailed info
6. `developer-tools-yaml.png` - Developer tools YAML tab
7. `developer-tools-states.png` - Entity states viewer
8. `light-control-dialog.png` - Light brightness control modal

## Recommendations for Development

### Testing Workflow

1. Use the Developer Tools → States tab to monitor entity state changes in real-time
2. Test device commands through the Overview UI and verify MQTT messages
3. Check the CyncLAN Bridge logs via Settings → Add-ons → CyncLAN Bridge → Log tab
4. Use the Actions tab to manually trigger service calls for testing

### Integration Points

The CyncLAN integration exposes entities through MQTT discovery following the Home Assistant MQTT JSON schema. Key entity types:
- `binary_sensor.*` - Status indicators
- `button.*` - Action triggers
- `light.*` - Light controls with brightness
- `fan.*` - Fan controls
- `number.*` - Numeric inputs (like OTP)

### Browser Testing Capabilities

The Playwright integration allows automated testing of:
- Login flows
- Device control interactions (clicking switches, adjusting brightness)
- Export workflow testing (OTP submission)
- Navigation and UI state verification
- Screenshot capture for documentation

## Next Steps for Agents

When working with this Home Assistant instance:

1. **Check Logs First** - Navigate to Settings → Add-ons → CyncLAN Bridge → Log to diagnose issues
2. **Monitor MQTT** - Use EMQX interface or MQTT developer tools to inspect messages
3. **Verify DNS** - Ensure DNS redirection is properly configured for device communication
4. **Test Export Flow** - Walk through the device export process to ensure token caching works
5. **State Monitoring** - Use Developer Tools → States to watch real-time entity updates
6. **Service Testing** - Use Developer Tools → Actions to manually trigger CyncLAN services

## Browser Automation Notes

- Login credentials are stored in `hass-credentials.env` (not committed to git)
- The UI uses Web Components and Shadow DOM in some areas (may require special handling)
- Modal dialogs can be closed with `Escape` key
- Some elements have overlapping click targets (use Playwright's element references for precision)
- The sidebar can be toggled for more screen space
