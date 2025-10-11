# Testing Plan: Mode Control Command Implementation

## What We Know
- ✅ Mode control byte location (byte 33 in 0x73 packet)
- ✅ Mode values: 0x50 = Traditional, 0xb0 = Smart
- ✅ Packet structure documented

## What We Need to Test

### Phase 1: Checksum Reverse Engineering
**Goal:** Figure out how byte 41 (checksum) is calculated

**Approach:**
1. Compare multiple captured packets with same structure
2. Identify checksum algorithm (XOR, CRC, simple sum, etc.)
3. Implement checksum calculation function

**Test Cases:**
- Smart → Traditional packet (checksum = 0x87)
- Traditional → Smart packet (checksum = 0xf2)

### Phase 2: Packet Crafting
**Goal:** Create valid 0x73 packets from scratch

**Requirements:**
1. Device endpoint (1b dc da 3e)
2. Correct sequence/counter values
3. Valid checksum
4. Proper 0x7e framing

**Implementation Options:**
- Python script using socket connection
- Modify cync-lan to add `send_raw_packet()` method
- Create standalone testing tool

### Phase 3: Command Sending Test
**Goal:** Send crafted packet to device and verify response

**Test Procedure:**
1. Device starts in Traditional mode (0x50)
2. Send 0x73 packet with mode = 0xb0 (Smart)
3. Listen for 0x7b ACK response
4. Verify device relay is disabled
5. Check Home Assistant state updates

**Success Criteria:**
- ✅ Device ACKs the command (0x7b response)
- ✅ Device sends confirmation with new mode byte
- ✅ Physical relay behavior changes
- ✅ No device disconnection or errors

### Phase 4: Integration Testing
**Goal:** Integrate into cync-lan library

**Tasks:**
1. Add `set_smart_bulb_mode(device_id, mode)` method
2. Add mode detection on device status packets
3. Expose to Home Assistant as switch entity
4. Test mode persistence across power cycles

## Risks & Unknowns

⚠️ **Things That Could Go Wrong:**
1. **Checksum algorithm** - Might be complex (CRC-16, proprietary)
2. **Device authentication** - Cloud might sign/encrypt some fields
3. **Rate limiting** - Device might reject rapid mode changes
4. **Firmware variations** - Different switches might need different packets
5. **Bricking risk** - Invalid packets could potentially crash device firmware

## Current Blockers

🚧 **Before we can test:**
1. Need to implement checksum calculation
2. Need direct socket access to device (bypass cloud)
3. Should create backup/recovery plan in case device becomes unresponsive

## Next Immediate Steps

1. **Analyze checksum** - Look at the captured packets and reverse engineer byte 41
2. **Create test script** - Python script to send crafted 0x73 packet
3. **Test in isolated environment** - Use one switch as guinea pig
4. **Document results** - Record what works and what doesn't

---

**Question for user:** Should we proceed with checksum analysis and create a test script, or wait until we have a keypad switch to capture the third mode?
