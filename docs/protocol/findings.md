# Cync Switch Mode Configuration - Reverse Engineering Results

**Initial Date:** October 7, 2025
**Completed:** October 11, 2025
**Objective:** Reverse engineer TCP-based smart bulb mode configuration for Cync wired switches

## 🎉 SUCCESS: Full Mode Control Achieved

✅ **We have successfully reverse engineered the complete mode switching protocol!**

Smart bulb mode can now be controlled programmatically via TCP/cloud protocol when Bluetooth is disabled. Working injection commands have been tested and confirmed functional.

### Quick Reference: Mode Switch Commands

For device 160 (adapt device ID and counter for other devices):

#### Traditional Mode

````text
73 00 00 00 1e 1b dc da 3e 00 3a 00 7e 3d 01 00 00 f8 8e 0c 00 3e 01 00 00 00 a0 00 f7 11 02 01 01 85 7e
```text

### Smart (Dimmable) Mode

```text
73 00 00 00 1e 1b dc da 3e 00 29 00 7e 30 01 00 00 f8 8e 0c 00 31 01 00 00 00 a0 00 f7 11 02 01 02 79 7e
```text

See [mode_change_analysis.md](./mode_change_analysis.md) for complete details and testing methodology.

---

## Initial Discovery

✅ **Smart bulb mode CAN be controlled via TCP/cloud protocol when Bluetooth is disabled!**

## The Mode Control Byte

**Location:** Byte 31 in the 0x73 packet payload (Device → Cloud confirmation packet)

### Values

- `0x50` = **Traditional Mode** (power relay ENABLED, works with dumb bulbs)
- `0xb0` = **Smart Mode (Dimmable)** (power relay DISABLED, smart bulb compatible)
- `0x??` = **Smart Mode (Non-Dimmable)** - Not yet captured

## Packet Structure

### Full 0x73 Configuration Packet (43 bytes total)

```text
Position  Bytes                           Description
--------  ------------------------------  ----------------------------------
0-4       73 00 00 00 26                  Packet type (0x73) + length (38)
5-11      1b dc da 3e 01 XX 00           Endpoint (device ID + counter)
12        7e                              Start marker
13-16     YY 01 00 00                     Command header
17-19     fa 8e 14                        Subcommand (config change)
20-21     00 ZZ                           Unknown
22-23     04 00                           Unknown
24-25     a0 00                           Device/Group ID #1
26-27     4c 00                           Device/Group ID #2
28-30     ea 11 02                        Unknown
31        a0                              Constant?
32        81                              Constant?
33        MODE                            ⭐ MODE CONTROL BYTE ⭐
34-39     00 00 00 00 00 00              Padding/reserved
40        14                              Unknown
41        XX                              Checksum
42        7e                              End marker
```text

## Captured Examples

### Smart → Traditional Mode

```yaml
File: smart_to_traditional.txt, Line 238-241
Timestamp: 2025/10/07 20:24:27

73 00 00 00 26 1b dc da 3e 01 00 00 7e 23 01 00
00 fa 8e 14 00 73 04 00 a0 00 4c 00 ea 11 02 a0
81 50 00 00 00 00 00 00 14 87 7e
   ^^                                    Mode = 0x50 (Traditional)
```text

### Traditional → Smart Mode

```yaml
File: traditional_to_smart.txt, Line 2272-2275
Timestamp: 2025/10/07 20:31:26

73 00 00 00 26 1b dc da 3e 01 3a 00 7e 36 01 00
00 fa 8e 14 00 7e 04 00 a0 00 4c 00 ea 11 02 a0
81 b0 00 00 00 00 00 00 14 f2 7e
   ^^                                    Mode = 0xb0 (Smart Dimmable)
```text

## Communication Flow

1. **User changes mode in Cync app** (with Bluetooth OFF)
2. **App → Cloud:** Mode change request
3. **Cloud → Device:** 0x73 packet with configuration command
4. **Device → Cloud:** 0x7b ACK packet
5. **Device → Cloud:** 0x73 confirmation packet with new mode byte
6. **Cloud → Device:** Final acknowledgment

## Implementation Potential

This discovery enables the cync-controller project to:

1. ✅ **Query current mode** - Parse 0x73 packets to detect current relay mode
2. ✅ **Change mode via TCP** - Send properly formatted 0x73 packets to switch modes
3. ✅ **Disable relay remotely** - Set Smart mode (0xb0) to prevent power cycling smart bulbs
4. ✅ **Enable relay remotely** - Set Traditional mode (0x50) for normal switch operation

## Technical Notes

- Configuration changes work over **TCP/cloud connection** when Bluetooth is disabled
- The **device sends confirmation** back to cloud with the new mode setting
- Mode changes are **persistent** (stored in device firmware)
- The **0x73 packet type** is a bi-directional data channel (documented in packet_structure.md)
- **Checksum calculation** needs to be reverse-engineered for sending commands

## Testing Environment

- **MITM Setup:** socat SSL proxy with self-signed certificates
- **DNS Hijacking:** cm.gelighting.com redirected to local proxy
- **Device:** Cync wired switch (ID: 0x1bdcda3e)
- **Firmware:** Current production firmware (as of Oct 2025)

## Future Work

1. Capture **Smart Non-Dimmable mode** byte value
2. **Reverse engineer checksum** algorithm for 0x73 packets
3. **Implement mode switching** in cync-controller Python library
4. Test with **different switch models** to confirm consistency
5. Document any **fade rate or other configuration** bytes in 0x73 packets

## Related Files

- `/mnt/supervisor/addons/local/hass-addons/mitm/smart_to_traditional.txt` - Full capture
- `/mnt/supervisor/addons/local/hass-addons/mitm/traditional_to_smart.txt` - Full capture
- `/mnt/supervisor/addons/local/hass-addons/mitm/mode_change_analysis.md` - Detailed analysis
- `/mnt/supervisor/addons/local/hass-addons/cync-controller/cync-controller-python/docs/packet_structure.md` - Protocol docs

---

**Conclusion:** The original assumption that smart bulb mode configuration was "Bluetooth-only" is **FALSE**. The feature CAN be implemented via the local TCP protocol! 🎉
````
