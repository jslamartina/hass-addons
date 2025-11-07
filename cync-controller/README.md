# Cync Controller

> **Note:** This project is forked from [@baudneo/hass-addons](https://github.com/baudneo/hass-addons)

**Local control for Cync/C by GE smart devices** - Control your lights, switches, and plugs via MQTT without cloud dependency.

## ⚠️ DNS Redirection Required

You **must** configure DNS redirection to route these domains to your Home Assistant server:

- `cm-sec.gelighting.com`
- `cm.gelighting.com`
- `cm-ge.xlink.cn`

### [📖 Complete DNS Setup Guide →](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/dns-setup.md)

Without DNS redirection, your devices will continue using the cloud and this add-on won't work.

## What This Add-on Provides

- **Device Exporter** - Web UI to export your device list from Cync cloud (2FA supported)
- **nCync Server** - TCP server that masquerades as the Cync cloud controller
- **MQTT Bridge** - Automatic Home Assistant MQTT discovery integration
- **🆕 Cloud Relay Mode** - MITM proxy for packet inspection and debugging

## Supported Devices

**Working:** Lights (tunable white, dimmable, on/off, full color), plugs, switches, fan controllers
**Not Supported:** Battery-powered devices (motion sensors, wire-free devices)
**Untested:** Cameras, thermostats

### [📖 Full Device Compatibility List →](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/known-devices.md)

## 🆕 New in v0.0.4.13

### Production-Grade Structured Logging

- **Dual-format output**: JSON for machine parsing, human-readable for developers
- **Correlation ID tracking** across async operations for debugging
- **Performance instrumentation** with configurable thresholds
- **Visual prefixes**: ═ ✓ → ⚠️ ✗ for quick log scanning

### Comprehensive Test Infrastructure

- **24 unit test files** covering all core modules (90%+ coverage)
- **10 E2E test files** using Playwright for browser automation
- **Integration tests** for mesh refresh performance

### Critical Bug Fixes

- Fixed OTP submission reliability (works on first try)
- Fixed restart button behavior and persistence
- Fixed group switch synchronization issues
- Fixed random device offline issues

### Cloud Relay Mode

Optional MITM proxy functionality for packet inspection and debugging:

- **Transparent proxy** between devices and cloud
- **Packet inspection** and real-time logging
- **File-based packet injection** for testing

### Configuration

```yaml
cloud_relay:
  enabled: false # Enable relay mode
  forward_to_cloud: true # Forward to cloud
  debug_packet_logging: false # Verbose logs
  disable_ssl_verification: false # Debug mode only
```

### [📖 Complete Cloud Relay Documentation →](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/cloud-relay.md)

### Enhanced MQTT Discovery

- **Name-based entity IDs** instead of numeric IDs
- **Color mode compliance** for Home Assistant 2025.3+
- **Smart area grouping** based on device names
- **Improved device metadata** with manufacturer and model info

## Quick Start

See the **Documentation** tab above for first-run steps and detailed instructions.

## 📚 Documentation

- **[DNS Setup Guide](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/dns-setup.md)** - Required setup
- **[Troubleshooting](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/troubleshooting.md)** - Common issues
- **[Tips & Best Practices](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/tips.md)** - Optimize your setup
- **[Cloud Relay Mode](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/cloud-relay.md)** - Advanced features
- **[Complete Documentation Index](https://github.com/jslamartina/hass-addons/blob/dev/docs/README.md)** - All documentation
