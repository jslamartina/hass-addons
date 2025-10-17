![Local Push Polling][polling-shield]

# CyncLAN Bridge

**Local control for Cync/C by GE smart devices** - Control your lights, switches, and plugs via MQTT without cloud dependency.

## ⚠️ DNS Redirection Required

You **must** configure DNS redirection to route these domains to your Home Assistant server:
- `cm-sec.gelighting.com`
- `cm.gelighting.com`
- `cm-ge.xlink.cn`

**[📖 Complete DNS Setup Guide →](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/dns-setup.md)**

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

**[📖 Full Device Compatibility List →](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/known-devices.md)**

## 🆕 New in v0.0.4.4

### Cloud Relay Mode (WIP)
Optional MITM proxy functionality for packet inspection and debugging:
- **Transparent proxy** between devices and cloud
- **Packet inspection** and real-time logging
- **Multiple operating modes** for different use cases
- **File-based packet injection** for testing

**Configuration:**
```yaml
cloud_relay:
  enabled: false                      # Enable relay mode
  forward_to_cloud: true              # Forward to cloud
  debug_packet_logging: false         # Verbose logs
  disable_ssl_verification: false     # Debug mode only
```

**[📖 Complete Cloud Relay Documentation →](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/cloud-relay.md)**

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