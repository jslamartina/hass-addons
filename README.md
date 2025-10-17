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

### Supported Devices

- ✅ Lights (tunable white, dimmable, on/off)
- ✅ Switches (dimmer, 3-way, 4-way)
- ✅ Plugs
- ❌ Battery-powered devices (motion sensors, wire-free switches)

**[Full compatibility list →](docs/user/known-devices.md)**

## 🛠️ Development

```bash
# Quick commands for developers
ha addons logs local_cync-lan     # View logs
./scripts/configure-addon.sh      # Configure addon
ha addons restart local_cync-lan  # Restart addon
npm run lint                      # Run all linters
npm run lint:python:fix           # Auto-fix Python issues
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
