# CyncLAN Bridge
CyncLAN bridge is a software stack that allows Home Assistant to communicate with Cync (formerly C by GE) 
smart devices over a local network connection, bypassing the need for cloud services.
This add-on uses MQTT for communication and supports auto-discovery of devices in Home Assistant.

You must use [DNS redirection](https://github.com/baudneo/hass-addons/tree/dev/docs/cync-lan/DNS.md) to forward: 
- `cm-sec.gelighting.com`
- `cm.gelighting.com`
- `cm-ge.xlink.cn`

to your Home Assistant server's local IP address. This will trick Cync devices into connecting to the `nCync` 
(say: _bye, bye, bye_ to Cloud only) TCP socket server running in this add-on, enabling you to control your devices locally.

>[!NOTE]
> You will still need to use the Cync app to add new devices to your Cync account. 
> Once added and a new config is exported, you can control the newly added devices locally


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
In order to perform a seemless migration from the old monolithic, non add-on setup:
- SSH into the host or get to the CLI on the device
- create a folder to hold the config in the correct location: `mkdir -p /homeassistant/.storage/cync-lan/config`
- copy your existing `cync_mesh.yaml` into the new dir: `cp /path/to/cync_mesh.yaml /homeassistant/.storage/cync-lan/config`

## Exporting Device Configuration
Visit the CyncLAN 'ingress' webpage (from the sidebar, or from the add-on page `Open Web UI` button). You will be greeted with a simple form that has provisions for being sent an OTP and to enter and submit the OTP.

- The `Start Export` button will check for a cached access token and use it to export your device config, removing the need for an OTP email to be sent
- The `Submit OTP` button will evaluate the OTP textbox and send the OTP to the backend export server
    - You can also request an OTP from the Cync app and then use the Submit OTP button, bypassing the `Start Export` button.
    - After submitting an OTP, the backend will use the OTP and Cync account creds to generate a new access token
    - The access token and metadata are stored on disk in a cache for future operations (Cync sets a 24 hr expiration on new access tokens)
    - Cync cloud API supplies a refresh token, but I need to figure out the endpoint and data structure to use it for renewing access tokens 
- The `Request OTP` button is for manually requesting an OTP to be sent to your Cync account email address, you should never really need to use this button
- After a successful export, the `cync_mesh.yaml` contents will be displayed in a text-box with syntax highlighting (via PRISM) and a `Download Config File` button will be available to allow downloading the newly exported config


## Tips / Troubleshooting
See the [tips documentation](https://github.com/baudneo/hass-addons/tree/dev/docs/cync-lan/tips.md) for tips on how to have a better experience with the add-on.

See the [troubleshooting documentation](https://github.com/baudneo/hass-addons/tree/dev/docs/cync-lan/troubleshooting.md) for common issues and how to resolve them.