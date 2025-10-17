# Home Assistant CyncLAN Add-ons

Local control for Cync/C by GE smart devices without cloud dependency.

## 🚀 Quick Start

### Installation

1. **Add this repository to Home Assistant:**
   - Settings → Add-ons → Add-on Store (bottom right ⋮ menu)
   - Add repository URL: `https://github.com/jslamartina/hass-addons`

2. **Install CyncLAN Bridge add-on**

3. **⚠️ Configure DNS redirection** (Required!)
   - See **[DNS Setup Guide](docs/user/dns-setup.md)** for detailed instructions
   - Without this, your devices will continue using the cloud

4. **Export your device configuration**
   - Open the add-on Web UI
   - Sign in with your Cync account credentials
   - Complete 2FA via email OTP
   - Download the generated configuration

5. **Start the add-on and enjoy local control!**

## 📚 Documentation

**Quick Links:**
- **[DNS Setup](docs/user/dns-setup.md)** - **Required setup** for local control
- **[Troubleshooting](docs/user/troubleshooting.md)** - Common issues and solutions
- **[Documentation Index](docs/README.md)** - Complete documentation guide
- **[Developer Guide](AGENTS.md)** - For developers and AI agents

## 🏠 What's Included

### CyncLAN Bridge Add-on

Control Cync devices locally by intercepting their cloud communications:
- **Device Exporter** - Web UI for exporting device config from Cync cloud
- **nCync Server** - TCP server masquerading as Cync cloud (requires DNS redirection)
- **MQTT Bridge** - Automatic Home Assistant integration via MQTT discovery
- **🆕 Cloud Relay Mode** - MITM proxy for packet inspection and debugging

### Supported Devices

- ✅ Lights (tunable white, dimmable, on/off, full color)
- ✅ Switches (dimmer, 3-way, 4-way, fan controllers)
- ✅ Plugs
- ❌ Battery-powered devices (motion sensors, wire-free switches)

**[Full compatibility list →](docs/user/known-devices.md)**

## 🆕 New in v0.0.4.4 (WIP)

### Cloud Relay Mode
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

**[📖 Complete Cloud Relay Documentation →](docs/user/cloud-relay.md)**

### Enhanced Development Environment
- **MCP Integration** - Advanced AI agent development tools
- **Ruff Linting** - 10-100x faster Python linting and formatting
- **Automated Testing** - Comprehensive test suites for all features
- **Programmatic Configuration** - Supervisor API-based configuration tools

## 🛠️ Development

```bash
# Quick commands for developers
ha addons logs local_cync-lan     # View logs
./scripts/configure-addon.sh      # Configure addon
ha addons restart local_cync-lan  # Restart addon
npm run lint                      # Run all linters
npm run lint:python:fix           # Auto-fix Python issues
```

**Enhanced Development Tools:**
```bash
# Programmatic configuration
./scripts/configure-addon.sh preset-relay-debug

# Comprehensive testing
./scripts/test-cloud-relay.sh

# Fresh HA setup automation
./scripts/setup-fresh-ha.sh
```

**[→ Full Developer Guide (AGENTS.md)](AGENTS.md)**

## 📖 Documentation Structure

```
docs/
├── user/              # User guides (DNS setup, troubleshooting, tips)
├── developer/         # Developer docs (testing, entity management, CLI)
├── protocol/          # Protocol research and reverse engineering
└── archive/           # Historical documentation
```

**[→ Complete Documentation Index](docs/README.md)**

## 🤝 Contributing

See **[AGENTS.md](AGENTS.md)** for:
- Development environment setup
- Coding conventions and standards
- Testing procedures
- PR guidelines

## 📝 License

See [LICENSE](LICENSE) for details.

## 🔗 Links

- **Repository:** https://github.com/jslamartina/hass-addons
- **Issues:** https://github.com/jslamartina/hass-addons/issues
- **Home Assistant:** https://www.home-assistant.io/

---

**⚠️ Important:** This add-on requires DNS redirection. See the [DNS Setup Guide](docs/user/dns-setup.md) before installation.

[polling-shield]: https://img.shields.io/badge/Local%20Push%20Polling-0.0.4-blue.svg
