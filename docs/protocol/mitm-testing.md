# MITM Proxy with Injection - Testing Guide

**Last Updated:** October 11, 2025

## ⚠️ SECURITY WARNING

**See [README.md](./README.md) for critical security warnings.** This tool disables SSL verification and is for LOCAL DEBUGGING ONLY.

---

## Overview

This is a **practical operations guide** for using the MITM proxy with injection capability to test smart bulb mode changes on Cync switches.

**Primary Use Case:** Change switch modes (Smart ↔ Traditional) to restore dimmable functionality.

**For Protocol Details:** See [FINDINGS_SUMMARY.md](./FINDINGS_SUMMARY.md) for packet analysis and [mode_change_analysis.md](./mode_change_analysis.md) for captured examples.

### 🎉 Status: WORKING

As of **October 11, 2025**, mode switching has been successfully reverse engineered and tested. The commands below will reliably switch Cync switches between Traditional and Smart modes when injected through the MITM proxy. See the complete protocol analysis in the documentation files linked above.

---

## Prerequisites

### 1. SSL Certificates

The MITM proxy requires SSL certificates to decrypt device traffic:

```bash
cd /mnt/supervisor/addons/local/hass-addons/mitm
ls -la certs/server.pem
```

If certificates don't exist, generate them:
```bash
./create_certs.sh
```

### 2. Port Availability

The MITM proxy listens on **port 23779** (same as Cync cloud). You must stop any service using this port:

**Check port status:**
```bash
lsof -i :23779
# or
netstat -tlnp | grep 23779
```

**Stop CyncLAN Add-on (if running):**
```bash
docker stop addon_local_cync-controller
```

### 3. DNS Redirection

Ensure your router/DNS is configured to redirect Cync cloud domains to your local machine:
- `cm.gelighting.com` → Your local IP
- `cm-sec.gelighting.com` → Your local IP
- `cm-ge.xlink.cn` → Your local IP

See [DNS.md](../docs/user/dns-setup.md) for detailed instructions.

---

## Starting the MITM Proxy

### Method 1: Using the Helper Script (Recommended)

```bash
cd /mnt/supervisor/addons/local/hass-addons/mitm
./run_mitm.sh
```

### Method 2: Direct Python Execution

```bash
cd /mnt/supervisor/addons/local/hass-addons/mitm
python3 mitm_with_injection.py 2>&1 | tee mitm_proxy.log
```

### Method 3: Background Execution

```bash
cd /mnt/supervisor/addons/local/hass-addons/mitm
python3 mitm_with_injection.py > mitm_proxy.log 2>&1 &
```

### Expected Startup Output

```
[08:17:57] ============================================================
[08:17:57] Cync MITM Proxy with Packet Injection
[08:17:57] ============================================================
[08:17:57] Listening on port 23779...
[08:17:57] Forwarding to 35.196.85.236:23779
[08:17:57] Type 'smart' or 'traditional' and press Enter to inject packet
```

---

## Monitoring Device Connections

### Real-time Log Monitoring

In a separate terminal:
```bash
tail -f /mnt/supervisor/addons/local/hass-addons/mitm/mitm_proxy.log
```

### What to Look For

**Device Connections:**
```
[08:18:03] Device connected from ('172.67.135.131', 17179)
[08:18:03] SSL handshake complete with device
[08:18:03] Connected to cloud server 35.196.85.236:23779
[08:18:03] Device endpoint: 64 a4 f2 da
```

**Target Device Discovery (Device 160 - Hallway 4way Switch):**
```
🎯 FOUND TARGET SWITCH! Device ID: 160 (Hallway 4way Switch)
   Home/User Endpoint: 1b dc da 3e
```

**Injection Capability:**
```
[INJECT] This connection (EP:64 57 e7 f2) handles device 160 - injection enabled
```

or

```
[INJECT] This connection (EP:64 a4 f2 da) is not for device 160 - injection disabled
```

**Device Status Updates:**
```
[08:18:22] [DEV->CLOUD] 0x43 DEVICE_INFO | LEN:52
  Devices: 160 (0xa0), 76 (0x4c)
  Device Statuses (2 devices):
    [160] ON  Bri: 33 Temp: 50 Online:True
    [ 76] OFF Bri:  0 Temp:  0 Online:True
```

---

## Injecting Mode Change Commands ✅

**Status: VERIFIED WORKING** - These commands have been successfully tested and confirmed functional.

### Option 1: Using the Helper Script (Recommended)

**Switch to Smart (Dimmable) Mode:**
```bash
cd /mnt/supervisor/addons/local/hass-addons/mitm
./inject_mode.sh smart
```

**Switch to Traditional (On/Off) Mode:**
```bash
./inject_mode.sh traditional
```

### Option 2: Direct File Write

**Smart Mode:**
```bash
echo "smart" > /mnt/supervisor/addons/local/hass-addons/mitm/inject_command.txt
```

**Traditional Mode:**
```bash
echo "traditional" > /mnt/supervisor/addons/local/hass-addons/mitm/inject_command.txt
```

### Option 3: Raw Packet Injection (Advanced)

For testing with exact packet bytes or custom commands. These are the **verified working commands** for device 160:

**Switch to Traditional Mode:**
```bash
./inject_raw.sh '73 00 00 00 1e 1b dc da 3e 00 3a 00 7e 3d 01 00 00 f8 8e 0c 00 3e 01 00 00 00 a0 00 f7 11 02 01 01 85 7e'
```

**Switch to Smart (Dimmable) Mode:**
```bash
./inject_raw.sh '73 00 00 00 1e 1b dc da 3e 00 29 00 7e 30 01 00 00 f8 8e 0c 00 31 01 00 00 00 a0 00 f7 11 02 01 02 79 7e'
```

**Note:** Device ID is `a0 00` (160) and mode byte is the second-to-last byte before the final `7e`:
- `01` = Traditional mode
- `02` = Smart/Dimmable mode

---

## Expected Injection Behavior

### Successful Injection Log Output

```
*** INJECTING SMART MODE PACKET TO DEVICE 160 ***
    Using counter: 0x15
INJECT: 73 00 00 00 1e 1b dc da 3e 00 15 00 7e 10 01 00 00 f8 8e 0c 00 11 01 00 00 00 a0 00 f7 11 02 01 02 59 7e
*** INJECTION COMPLETE ***
Watching for device response...
```

### Device Response

The device will acknowledge with a 0x7b ACK packet:
```
[DEV->CLOUD] 0x7b ACK
```

Followed by a status update showing the new mode:
```
[DEV->CLOUD] 0x73 CONFIG_RESPONSE
[MODE DETECTED] Device 160: SMART/DIMMABLE (0xb0)
```

### Physical Behavior

**After Smart Mode Injection:**
- ✅ Switch becomes dimmable in Home Assistant
- ✅ Brightness slider functional
- ✅ Light responds to dimming commands
- ⚠️ Physical switch press = toggle only (no dimming)

**After Traditional Mode Injection:**
- ❌ Switch becomes on/off only
- ❌ Brightness slider disabled/ignored
- ✅ Physical switch functions normally

---

## Troubleshooting

### Problem: Port Already in Use

**Symptom:**
```
OSError: [Errno 98] Address already in use
```

**Solution:**
1. Check what's using the port:
   ```bash
   lsof -i :23779
   netstat -tlnp | grep 23779
   ```

2. Stop the CyncLAN add-on:
   ```bash
   docker ps --filter "name=addon_local_cync-controller"
   docker stop addon_local_cync-controller
   ```

3. Restart the MITM proxy

### Problem: Target Device Not Connecting

**Symptom:**
All devices show "injection disabled"

**Possible Causes:**
1. **DNS not configured** - Devices going directly to cloud
2. **Wrong endpoint** - Device 160 connects through a different bridge device
3. **Device offline** - Switch is powered off or disconnected

**Solutions:**
1. Verify DNS redirection:
   ```bash
   dig cm.gelighting.com
   # Should return your local IP
   ```

2. Check device power and connectivity

3. Toggle the physical switch to force reconnection

4. Review captured endpoints in logs to identify which connection handles device 160

### Problem: Injection Has No Effect

**Symptom:**
Packet injected but mode doesn't change

**Possible Causes:**
1. **Wrong packet counter** - Out of sync with cloud
2. **Incorrect checksum** - Packet rejected
3. **Wrong endpoint** - Sent to wrong device

**Solutions:**
1. Check the logs for counter values:
   ```
   [COUNTER] Initialized Cloud->Dev counter at 0x15
   ```

2. Verify checksum calculation in logs

3. Ensure injection is targeting the correct endpoint (1b dc da 3e for user ID 467458622)

### Problem: Devices Disconnect Frequently

**Symptom:**
Constant reconnections in logs

**Possible Causes:**
1. **SSL handshake issues** - Certificate problems
2. **Network instability** - WiFi signal
3. **Cloud timeout** - Slow connection to real cloud

**Solutions:**
1. Regenerate certificates:
   ```bash
   ./create_certs.sh
   ```

2. Check network stability

3. Ensure cloud server (35.196.85.236) is reachable

---

## Understanding the Protocol

**For detailed protocol documentation, see:**
- [FINDINGS_SUMMARY.md](./FINDINGS_SUMMARY.md) - Complete packet type reference and structure
- [mode_change_analysis.md](./mode_change_analysis.md) - Captured packet examples with annotations

**Quick Reference:**
- **Mode Bytes:** `0x01` = Traditional (relay on), `0x02` = Smart (relay off)
- **User Endpoint:** `1b dc da 3e` (user ID 467458622)
- **Device 160:** Hallway 4way Switch (`a0 00` in little-endian)

---

## Restoring Normal Operation

### 1. Stop the MITM Proxy

**If running in foreground:**
```bash
Ctrl+C
```

**If running in background:**
```bash
pkill -f mitm_with_injection.py
# or
ps aux | grep mitm_with_injection
kill <PID>
```

### 2. Restart the CyncLAN Add-on

```bash
docker start addon_local_cync-controller
```

Or via Home Assistant UI:
1. Go to **Settings** → **Add-ons**
2. Click **CyncLAN Bridge**
3. Click **Start**

### 3. Verify Operation

Check that devices reconnect and function normally:
1. **Home Assistant:** Check device states in Overview
2. **Add-on Logs:** Monitor connection status
3. **Physical Test:** Toggle switches and verify response

---

## Advanced Testing Scenarios

### Capturing Mode Changes from App

1. Start MITM proxy with capture enabled
2. Use official Cync app to change mode
3. Analyze captured packets in logs
4. See [mode_change_analysis.md](./mode_change_analysis.md) for examples

### Testing Multiple Devices

To inject commands to different devices, modify the target device ID in `mitm_with_injection.py`:
- Device 160 (Hallway 4way): `0xa0 0x00`
- Device 76: `0x4c 0x00`

---

## Log Analysis Tips

### Useful grep Commands

**Find target device:**
```bash
grep "FOUND TARGET SWITCH" mitm_proxy.log
```

**Track mode changes:**
```bash
grep "MODE DETECTED" mitm_proxy.log
```

**Monitor injections:**
```bash
grep "INJECTING" mitm_proxy.log
```

**Check device status:**
```bash
grep "Device Statuses" mitm_proxy.log
```

**View only errors:**
```bash
grep -i "error" mitm_proxy.log
```

### Common Log Patterns

**Successful Connection:**
```
Device connected from → SSL handshake complete → Connected to cloud server
```

**Mode Change Sequence:**
```
INJECTING SMART MODE → INJECTION COMPLETE → 0x7b ACK → MODE DETECTED: SMART
```

**Keepalive Pattern:**
```
[CLOUD->DEV] 0x78 KEEPALIVE (every 5 seconds)
```

---

## Performance Notes

- **Latency:** +5-10ms added by MITM proxy
- **Stability:** Connections stable for hours
- **CPU Usage:** ~1-2% on modern hardware

**Tip:** Use wired connection and run on same machine as Home Assistant for best performance.

---

## References

**Documentation:**
- [README.md](./README.md) - Security warnings and file overview
- [FINDINGS_SUMMARY.md](./FINDINGS_SUMMARY.md) - Complete protocol analysis
- [mode_change_analysis.md](./mode_change_analysis.md) - Captured packet examples
- [DNS Setup](../docs/user/dns-setup.md) - DNS redirection configuration

**Key Scripts:**
- `mitm_with_injection.py` - Main MITM proxy
- `inject_mode.sh` - Mode injection helper
- `run_mitm.sh` - Startup script

---

## Quick Reference Card

### Start MITM
```bash
cd /mnt/supervisor/addons/local/hass-addons/mitm
docker stop addon_local_cync-controller
python3 mitm_with_injection.py 2>&1 | tee mitm_proxy.log
```

### Monitor Logs
```bash
tail -f mitm_proxy.log
```

### Inject Smart Mode
```bash
./inject_mode.sh smart
```

### Inject Traditional Mode
```bash
./inject_mode.sh traditional
```

### Stop MITM
```bash
# Ctrl+C (if foreground)
# or
pkill -f mitm_with_injection.py
```

### Restore Normal
```bash
docker start addon_local_cync-controller
```

---

**Happy Testing! 🔍🔧**

Remember: This is a debugging tool. Use responsibly and only in controlled environments.

