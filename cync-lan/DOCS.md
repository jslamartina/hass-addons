The CyncLAN bridge is a software stack that allows Home Assistant to communicate with Cync (formerly C by GE) 
smart devices over a local network connection, bypassing the need for cloud services. 
This add-on uses MQTT for communication and supports auto-discovery of devices in Home Assistant.

You must use DNS redirection to forward: `cm-sec.gelighting.com` | `cm.gelighting.com` | `cm-ge.xlink.cn` 
to your Home Assistant server's local IP address. This will trick Cync devices into connecting to the `nCync` 
(say: _bye, bye, bye_ to Cloud only) TCP socket server running in this add-on, allowing you to control your devices locally.

>[!NOTE]
> You will still need to use the Cync app to add new devices to your Cync account. 
> Once added and a new config is exported, you can control the newly added devices locally

## Prerequisites
- DNS redirection is required. See the [DNS documentation](https://github.com/baudneo/hass-addons/tree/dev/docs/DNS.md)
- A Cync account with devices registered and a Cync app for managing your devices
- Home Assistant with the MQTT integration configured and MQTT auto-discovery enabled
- A MQTT broker (e.g., Mosquitto, EMQX) running and accessible from Home Assistant
- _Optional_: Firewall rules for VLANs, etc. to allow communication from the Cync devices to the Home Assistant server
- Export a device configuration from the Cync cloud API using the add-on's ingress page (See First Run Steps below)

## First Run Steps
>[!IMPORTANT]
> Before you can manage your devices locally, you must export your Cync device list from the Cync cloud API
> using the add-on's ingress page.

1. Configure the Cync account username, account password and MQTT broker connection details in the add-on configuration.
2. Start the add-on
3. Visit the ingress page of the add-on in Home Assistant
4. Click the "Export Devices" button
5. Follow the prompts, check your Cync account email for the OTP code and enter it into the ingress page form, click 'submit'
6. Wait for the success message indicating that the device list has been exported
7. Restart the add-on to load the newly exported configuration
8. MQTT auto-discovery will automatically create entities in Home Assistant for each device and a 'bridge' device to represent the CyncLAN controller itself
9. As long as DNS redirection is set up correctly and you power cycled your Wi-Fi Cync devices, all supported and discovered devices should now be controllable from Home Assistant (Even BTLE only devices!)

## Tips / Troubleshooting
See the [tips documentation](https://github.com/baudneo/hass-addons/docs/tips.md) for tips on how to have a better experience with the add-on.

See the [troubleshooting documentation](https://github.com/baudneo/hass-addons/docs/troubleshooting.md) for common issues and how to resolve them.