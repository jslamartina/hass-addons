# Home Assistant Cync Controller Add-ons

> **Note:** This project is now maintained independently; it was originally inspired by [@baudneo/hass-addons](https://github.com/baudneo/hass-addons).

Local control for Cync/C by GE smart devices without cloud dependency.

## 🚀 Quick Start

### Installation

1. **Add this repository to Home Assistant:**
   - Settings → Add-ons → Add-on Store (bottom right ⋮ menu)
   - Add repository URL: `https://github.com/jslamartina/hass-addons`

2. **Install Cync Controller add-on**

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

### Quick Links

- **[DNS Setup](docs/user/dns-setup.md)** - **Required setup** for local control
- **[Troubleshooting](docs/user/troubleshooting.md)** - Common issues and solutions
- **[Documentation Index](docs/README.md)** - Complete documentation guide
- **[Developer Guide](AGENTS.md)** - Rules system and navigation

## 🏠 What's Included

### Cync Controller Add-on

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

### [Full compatibility list →](docs/user/known-devices.md)

## 🆕 New in v0.0.4.13

### Production-Grade Structured Logging

- **Dual-format output**: JSON for machine parsing, human-readable for developers
- **Correlation ID tracking** across async operations for debugging
- **Performance instrumentation** with configurable thresholds

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

### [📖 Complete Cloud Relay Documentation →](docs/user/cloud-relay.md)

### Enhanced Development Environment

- **MCP Integration** - Advanced AI agent development tools
- **Ruff Linting** - 10-100x faster Python linting and formatting
- **Automated Testing** - Comprehensive test suites for all features
- **Programmatic Configuration** - Supervisor API-based configuration tools

## 🛠️ Development

```bash
## Quick commands for developers
ha addons logs local_cync-controller    # View logs
./scripts/configure-addon.sh            # Configure addon
ha addons restart local_cync-controller # Restart addon
npm run lint                            # Run all linters
npm run lint:python:fix                 # Auto-fix Python issues
```

### Enhanced Development Tools

```bash
## Programmatic configuration
./scripts/configure-addon.sh preset-relay-debug

## Comprehensive testing
./scripts/test-cloud-relay.sh

## Fresh HA setup automation
./scripts/setup-fresh-ha.sh
```

**[→ Cursor Rules Guide](.cursor/RULES_GUIDE.md)** for development workflow

## 📖 Documentation Structure

```text

docs/
├── user/              # User guides (DNS setup, troubleshooting, tips)
├── developer/         # Developer docs (testing, entity management, CLI)
├── protocol/          # Protocol research and reverse engineering
└── archive/           # Historical documentation

```

### [→ Complete Documentation Index](docs/README.md)

## 🤝 Contributing

See **[Cursor Rules](.cursor/RULES_GUIDE.md)** for:

- Development environment setup
- Coding conventions and standards
- Testing procedures
- PR guidelines

## 📝 License

See [LICENSE](LICENSE) for details.

## 🔗 Links

- **Repository:** <https://github.com/jslamartina/hass-addons>
- **Issues:** <https://github.com/jslamartina/hass-addons/issues>
- **Home Assistant:** <https://www.home-assistant.io/>

---

**⚠️ Important:** This add-on requires DNS redirection. See the [DNS Setup Guide](docs/user/dns-setup.md) before installation.
