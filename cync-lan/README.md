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

## Supported Devices

**Working:** Lights, plugs, switches
**Not Supported:** Battery-powered devices (motion sensors, wire-free devices)
**Untested:** Cameras, thermostats

**[📖 Full Device Compatibility List →](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/known-devices.md)**

## Quick Start

See the **Documentation** tab above for first-run steps and detailed instructions.

## 📚 Documentation

- **[DNS Setup Guide](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/dns-setup.md)** - Required setup
- **[Troubleshooting](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/troubleshooting.md)** - Common issues
- **[Tips & Best Practices](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/tips.md)** - Optimize your setup
- **[Cloud Relay Mode](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/cloud-relay.md)** - Advanced features