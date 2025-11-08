# Smart Bulb Mode Configuration Analysis

## ✅ SUCCESS: Mode Switching Commands Reverse Engineered

**Date:** October 11, 2025

We have successfully reverse engineered the Cync protocol commands to switch a switch between Smart (Dimmable) and Traditional modes!

### Working Commands for Device 160 (Hallway 4-Way Switch)

#### Switch to TRADITIONAL Mode

````text
73 00 00 00 1e 1b dc da 3e 00 3a 00 7e 3d 01 00 00 f8 8e 0c 00 3e 01 00 00 00 a0 00 f7 11 02 01 01 85 7e
```text

#### Switch to SMART (Dimmable) Mode

```text
73 00 00 00 1e 1b dc da 3e 00 29 00 7e 30 01 00 00 f8 8e 0c 00 31 01 00 00 00 a0 00 f7 11 02 01 02 79 7e
```text

### Packet Structure Breakdown

**Packet Type:** 0x73 (DATA_CHANNEL - Cloud to Device)

#### Key Components

- **Endpoint:** `1b dc da 3e` (User/Home ID)
- **Counter:** Variable (0x3a, 0x29, etc.) - increments with each command
- **Command:** `f8 8e 0c` (SET_MODE)
- **Device ID:** `a0 00` (160 in little-endian)
- **Mode Byte:**
  - `01` = Traditional (relay only)
  - `02` = Smart/Dimmable (PWM control enabled)
- **Checksum:** Last byte before closing `7e` marker

### Testing Method

Commands can be injected using the MITM proxy:

```bash
## Switch to Traditional mode
./inject_raw.sh '73 00 00 00 1e 1b dc da 3e 00 3a 00 7e 3d 01 00 00 f8 8e 0c 00 3e 01 00 00 00 a0 00 f7 11 02 01 01 85 7e'

## Switch to Smart mode
./inject_raw.sh '73 00 00 00 1e 1b dc da 3e 00 29 00 7e 30 01 00 00 f8 8e 0c 00 31 01 00 00 00 a0 00 f7 11 02 01 02 79 7e'
```text

The switch responds with a STATUS_BROADCAST (0x83) confirming the mode change.

---

## Historical Analysis: Test: Smart (Dimmable) → Traditional Mode

### Configuration Packets Captured (Bluetooth OFF)

**Time:** 2025/10/07 20:24:25 - 20:24:28

#### Packet 1: Cloud → Device (0x73)

```text

< 2025/10/07 20:24:25.000986640  length=35
73 00 00 00 1e 1b dc da 3e 00 1f 00 7e 23 01 00
00 f8 8e 0c 00 24 01 00 00 00 a0 00 f7 11 02 01
01 6b 7e

```text

### Decoded

- Packet type: 0x73 (bi-directional data channel)
- Endpoint: `1b dc da 3e 00 1f 00` (device ID: 0x1bdcda3e)
- Data (wrapped in 0x7e markers):
  - `7e 23 01 00 00 f8 8e 0c 00 24 01 00 00 00 a0 00 f7 11 02 01 01 6b 7e`

Device ACKs with 0x7b packet

#### Packet 2: Device → Cloud (0x73 response)

```sql

> 2025/10/07 20:24:26.000070842  length=24
73 00 00 00 13 1b dc da 3e 00 ff 00 7e 23 01 00
00 f9 8e 01 00 00 8f 7e

```text

#### Packet 3: Device → Cloud (0x73 - THE KEY PACKET!)

```text

> 2025/10/07 20:24:27.000217725  length=43
73 00 00 00 26 1b dc da 3e 01 00 00 7e 23 01 00
00 fa 8e 14 00 73 04 00 a0 00 4c 00 ea 11 02 a0
81 50 00 00 00 00 00 00 14 87 7e

```text

### Decoded

- Packet type: 0x73
- Endpoint: `1b dc da 3e 01 00 00` (device ID: 0x1bdcda3e)
- Data payload (between 0x7e markers):
  - Header: `7e 23 01 00 00`
  - `fa 8e 14` - command/subtype?
  - `00 73` - unknown
  - `04 00` - unknown
  - `a0 00` - device ID? (0xa0 = 160 decimal)
  - `4c 00` - device ID? (0x4c = 76 decimal)
  - `ea 11 02` - unknown
  - **`a0 81 50`** ← LIKELY THE MODE SETTING!
  - `00 00 00 00 00 00` - padding?
  - `14` - unknown
  - `87 7e` - checksum and end marker

#### Packet 4: Cloud → Device (0x73)

```sql

< 2025/10/07 20:24:27.000625507  length=23
73 00 00 00 12 1b dc da 3e 00 20 00 7e 25 01 00
00 f8 ea 00 00 ea 7e

```text

#### Packet 5: Device → Cloud (0x73)

```sql

> 2025/10/07 20:24:28.000067374  length=24
73 00 00 00 13 1b dc da 3e 01 01 00 7e 25 01 00
00 f9 ea 01 00 00 eb 7e

```text

## Key Findings

The critical bytes appear to be in **Packet 3**:

- Bytes `a0 81 50` (positions ~22-24 in the data payload)
- This is sent FROM the device TO the cloud (confirming the change)

## Next Steps

1. Capture another mode change (Traditional → Smart Dimmable) to compare
2. Capture Traditional → Non-Dimmable Smart to see the pattern
3. Identify which specific bytes control:
   - Traditional mode (relay ON)
   - Smart Dimmable mode (relay OFF, dimming enabled)
   - Smart Non-Dimmable mode (relay OFF, no dimming)

---

## Comparison: Traditional ↔ Smart Mode Changes

### Smart → Traditional (from smart_to_traditional.txt, line 238-241)

```sql

> 2025/10/07 20:24:27.000217725  length=43
73 00 00 00 26 1b dc da 3e 01 00 00 7e 23 01 00
00 fa 8e 14 00 73 04 00 a0 00 4c 00 ea 11 02 a0
81 50 00 00 00 00 00 00 14 87 7e
            ^^                        ^^
         Byte 22                   Byte 30

```text

### Traditional → Smart (from traditional_to_smart.txt, line 2272-2275)

```sql

> 2025/10/07 20:31:26.000833930  length=43
73 00 00 00 26 1b dc da 3e 01 3a 00 7e 36 01 00
00 fa 8e 14 00 7e 04 00 a0 00 4c 00 ea 11 02 a0
81 b0 00 00 00 00 00 00 14 f2 7e
   ^^          ^^                        ^^
Byte 22     Byte 30                  Byte 36

```text

## KEY FINDINGS - THE MODE CONTROL BYTE

Byte 30 (counting from start of 0x73 packet data payload):

- **`0x50`** = **Traditional Mode** (relay enabled, dumb bulb compatible)
- **`0xb0`** = **Smart Mode** (relay disabled, smart bulb mode)

### Packet Structure (0x73 configuration packet)

```text

Position 0-4:   73 00 00 00 26           - Packet header (0x73, length 0x26=38)
Position 5-11:  1b dc da 3e 01 XX 00    - Endpoint (device ID + counter)
Position 12:    7e                       - Start marker
Position 13-16: YY 01 00 00             - Command header
Position 17-19: fa 8e 14                - Subcommand
Position 20-21: 00 ZZ                    - Unknown
Position 22-23: 04 00                    - Unknown
Position 24-25: a0 00                    - Device ID (0xa0 = 160)
Position 26-27: 4c 00                    - Device ID (0x4c = 76)
Position 28-30: ea 11 02                 - Unknown
Position 31-33: a0 81 MODE              - **MODE BYTE HERE!**
Position 34-39: 00 00 00 00 00 00       - Padding
Position 40:    14                       - Unknown
Position 41-42: XX 7e                    - Checksum + end marker

```text

### Mode Values

- **0x50** = Traditional (relay ON for dumb bulbs)
- **0xb0** = Smart Dimmable (relay OFF, dimming enabled)
- **0x??** = Smart Non-Dimmable (TBD - need to capture this)

## Next Steps

To complete the reverse engineering:

1. Capture Smart Dimmable → Smart Non-Dimmable
2. Capture Smart Non-Dimmable → Traditional
3. Document all three mode byte values
4. Implement TCP-based mode switching in cync-controller!
````
