>[!IMPORTANT]
> DNS redirection is REQUIRED, please see [here](https://github.com/baudneo/cync-lan-addon/tree/dev/docs/DNS.md) for documentation and examples

![Local Push Polling][polling-shield]

CyncLAN is a software stack 'bridge' for Cync / C by GE smart devices, allowing you to control **supported** smart devices directly from Home Assistant.

This add-on provides:
- __exporter__: An async `fastapi` server that hosts a static ingress page and an API to export a device list from a Cync cloud account using 2FA (emailed OTP) [Token caching supported!]

- __nCync__: An async TCP socket server that *masquerades as the __Cync cloud controller__*

- __comms__: An async `aiomqtt` MQTT client for communication to HASS using the HASS MQTT JSON schema

# Supported devices
See [known devices](https://github.com/baudneo/cync-lan-addon/tree/dev/docs/known_devices.md)

#### MOSTLY SUPPORTED
- lights
- plugs
- switches

#### NOT SUPPORTED
- Any **battery** powered devices
    - motion sensors
    - *wire free* devices

#### UNTESTED
- Cameras
- Thermostat and temp sensors
- Dynamic functions (the lights should still work, just dont know about dynamic functions)



[polling-shield]: https://img.shields.io/badge/Polling-Local_Push-blue.svg
