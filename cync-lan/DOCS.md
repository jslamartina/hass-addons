# CyncLAN Bridge - Setup Guide

CyncLAN enables **local control** of Cync (C by GE) smart devices via MQTT, bypassing the cloud completely.

## ⚠️ Prerequisites

Before starting, you must set up **DNS redirection** to route these domains to your Home Assistant IP:
- `cm-sec.gelighting.com`
- `cm.gelighting.com`
- `cm-ge.xlink.cn`

**[📖 Complete DNS Setup Guide](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/dns-setup.md)** - Required reading

> **Note:** You'll still use the Cync app to add new devices. After adding devices, export a new config and restart this add-on.


## First Run Steps
>[!IMPORTANT]
> Before you can manage your devices locally, you must export your Cync device list from the Cync cloud API
> using the add-on's ingress page.

1. Configure the Cync account username, account password and MQTT broker connection details in the add-on configuration.
2. Start the add-on
3. Visit the ingress page of the add-on in Home Assistant (`Open Web UI` button near the add-on `UNINSTALL` button OR the lightbulb icon in the sidebar if you enabled `Show in sidebar`)
4. Click the "Start Export" button
5. Follow the prompts, check your Cync account email for the OTP code and enter it into the ingress page form, click 'submit'
6. Wait for the success message indicating that the device list has been exported
7. Restart the add-on to load the newly exported configuration
8. MQTT auto-discovery will automatically create entities in Home Assistant for each device and a 'bridge' device to represent the CyncLAN controller itself
9. As long as DNS redirection is set up correctly and you power cycled your Wi-Fi Cync devices, all supported and discovered devices should now be controllable from Home Assistant (Even BTLE only devices!)

## Migration
To perform a seamless migration from the old monolithic, non add-on setup:
- SSH into HASS or get to the CLI on the device
- create a folder to hold the config in the correct location: `mkdir -p /homeassistant/.storage/cync-lan/config`
- copy your existing `cync_mesh.yaml` into the new dir: `cp /path/to/cync_mesh.yaml /homeassistant/.storage/cync-lan/config`
- Start the add-on, it will automatically detect the existing config and use it
- Change your DNS redirection to point to the Home Assistant server's local IP address
- Power cycle the Cync devices, so they perform a DNS request and get the new IP address of the CyncLAN bridge

## Exporting Device Configuration
Visit the CyncLAN 'ingress' webpage (from the sidebar, or from the add-on page `Open Web UI` button). You will be greeted with a simple form that has provisions for being sent an OTP and to enter and submit the OTP.

**Using the Exporter:**

- **Start Export** - Automatically checks for cached credentials and exports without needing a new OTP
- **Submit OTP** - Enter the OTP code from your email and click to complete the export
- **Request OTP** - Manually request a new OTP email (rarely needed)

**After Export:**
- The config file contents will appear in a highlighted text box
- Click **Download Config File** to save it
- Restart the add-on to load the new configuration


## 📚 Additional Documentation

- **[Tips & Best Practices](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/tips.md)** - Optimize your setup
- **[Troubleshooting Guide](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/troubleshooting.md)** - Common issues and solutions
- **[Known Devices](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/known-devices.md)** - Device compatibility list
- **[Cloud Relay Mode](https://github.com/jslamartina/hass-addons/blob/dev/docs/user/cloud-relay.md)** - Advanced packet inspection features