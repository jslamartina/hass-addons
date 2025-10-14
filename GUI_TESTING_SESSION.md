# GUI Testing Session - Cloud Relay Mode Validation

**Date:** October 13, 2025
**Purpose:** Validate end-user experience with cloud relay mode active
**Home Assistant URL:** http://localhost:8123

---

## 🎯 Testing Objectives

This session validates that cloud relay mode doesn't break user-facing functionality and that devices respond correctly to GUI commands.

---

## 🚀 Quick Start

### Access Home Assistant
1. Open browser: **http://localhost:8123**
2. Login credentials: (check AGENTS.md or stored credentials)
3. Navigate to Overview dashboard

### Current System Status
- **Addon Version:** 0.0.4.0
- **Addon State:** Running
- **Cloud Relay:** Enabled (with forwarding)
- **Debug Logging:** As configured
- **Devices Connected:** 4+ devices

---

## ✅ Test Checklist

### Category 1: Basic Light Controls (5-10 minutes)

#### Test 1.1: On/Off Control
**Device:** Hallway Floodlight 1 (or any available light)

**Steps:**
1. [ ] Locate "Hallway Floodlight 1" entity
2. [ ] Click to turn **OFF**
   - **✓ Verify:** Light physically turns off within 2 seconds
   - **✓ Verify:** Entity icon changes to gray/off state
3. [ ] Click to turn **ON**
   - **✓ Verify:** Light physically turns on within 2 seconds
   - **✓ Verify:** Entity icon changes to yellow/on state
4. [ ] Check addon logs for relay activity:
   ```bash
   ha addons logs local_cync-lan -n 50 | grep -E "RELAY|0x73|0x83"
   ```

**Expected Result:** ✅ Light responds immediately, no errors

---

#### Test 1.2: Brightness Control
**Device:** Any tunable light (e.g., Hallway Floodlight 2)

**Steps:**
1. [ ] Click light entity to open control panel
2. [ ] Locate brightness slider (should show 0-100%)
3. [ ] Drag slider to **25%**
   - **✓ Verify:** Light dims to ~25% brightness
   - **✓ Verify:** Slider value updates
4. [ ] Set to **75%**
   - **✓ Verify:** Light brightens to ~75%
5. [ ] Set to **100%**
   - **✓ Verify:** Light at full brightness

**Expected Result:** ✅ Smooth brightness changes, GUI syncs with physical state

---

#### Test 1.3: Color Temperature Control
**Device:** Tunable white bulb (CLEDR309S2 model)

**Steps:**
1. [ ] Open light control panel
2. [ ] Locate color temperature slider (2000K - 7000K)
3. [ ] Set to **2000K** (warm white)
   - **✓ Verify:** Light appears warm/orange-ish
4. [ ] Set to **7000K** (cool white)
   - **✓ Verify:** Light appears cool/blue-ish
5. [ ] Set to **5000K** (neutral)
   - **✓ Verify:** Light appears neutral white

**Expected Result:** ✅ Color temperature changes are visible

---

### Category 2: Switch Controls (3-5 minutes)

#### Test 2.1: Switch Toggle
**Device:** Master Bedroom Fan Switch (or any switch)

**Steps:**
1. [ ] Locate switch entity
2. [ ] Toggle **OFF**
   - **✓ Verify:** Connected device turns off
3. [ ] Toggle **ON**
   - **✓ Verify:** Connected device turns on

**Expected Result:** ✅ Switch controls work correctly

---

#### Test 2.2: Dimmer Switch
**Device:** Hallway Front Switch (ID: 26) or Hallway Counter Switch (ID: 133)

**Steps:**
1. [ ] Locate dimmer switch entity
2. [ ] Adjust brightness slider
3. [ ] **✓ Verify:** Controlled lights dim/brighten accordingly

**Expected Result:** ✅ Dimmer controls responsive

---

### Category 3: Bidirectional Updates (5 minutes)

#### Test 3.1: Physical → GUI Update
**Device:** Any light with physical switch

**Steps:**
1. [ ] Note current state in Home Assistant GUI
2. [ ] **Physically toggle the wall switch or bulb**
3. [ ] Watch Home Assistant GUI (wait up to 10 seconds)
4. [ ] **✓ Verify:** Entity state updates automatically
5. [ ] Check Developer Tools → States → Find entity
6. [ ] **✓ Verify:** "Last Updated" timestamp is recent

**Expected Result:** ✅ Physical changes appear in GUI within 5-10 seconds

---

#### Test 3.2: Multiple Devices Update
**Steps:**
1. [ ] Physically change 2-3 devices at once
2. [ ] Observe GUI updates
3. [ ] **✓ Verify:** All entities update correctly

**Expected Result:** ✅ All state changes reflected

---

### Category 4: Addon Configuration UI (5-10 minutes)

#### Test 4.1: Cloud Relay Options Visible
**Steps:**
1. [ ] Navigate: Settings → Add-ons → CyncLAN Bridge
2. [ ] Click **"Configuration"** tab
3. [ ] Scroll to **cloud_relay** section
4. [ ] **✓ Verify** all options present:
   - [ ] enabled (toggle)
   - [ ] forward_to_cloud (toggle)
   - [ ] cloud_server (text)
   - [ ] cloud_port (number)
   - [ ] debug_packet_logging (toggle)
   - [ ] disable_ssl_verification (toggle)

**Expected Result:** ✅ All configuration options visible and editable

---

#### Test 4.2: Toggle Debug Logging via UI
**Steps:**
1. [ ] In Configuration tab, find **debug_packet_logging**
2. [ ] Toggle **ON** → Click **"Save"**
3. [ ] Click **"Info"** tab → Click **"Restart"**
4. [ ] Wait 15 seconds for restart
5. [ ] Click **"Logs"** tab
6. [ ] **✓ Verify:** Logs show detailed packet data:
   ```
   [DEV->CLOUD] 0x43 DEVICE_INFO | LEN:52
   [CLOUD->DEV] 0x48 INFO_ACK | LEN:3
   ```
7. [ ] Return to Configuration → Toggle debug_packet_logging **OFF**
8. [ ] Save and restart again
9. [ ] Check logs → **✓ Verify:** Packet details no longer appear

**Expected Result:** ✅ Configuration changes take effect after restart

---

### Category 5: Addon Management UI (5 minutes)

#### Test 5.1: Addon Info Display
**Steps:**
1. [ ] Navigate: Settings → Add-ons → CyncLAN Bridge
2. [ ] **Info** tab should show:
   - [ ] Version: **0.0.4.0**
   - [ ] State: **Running** (green)
   - [ ] Description mentions DNS requirement
   - [ ] Network ports: 23779, 23778

**Expected Result:** ✅ Info accurate and complete

---

#### Test 5.2: Logs Access & Filtering
**Steps:**
1. [ ] Click **"Logs"** tab
2. [ ] **✓ Verify:** Logs display immediately
3. [ ] Enable **"Follow"** checkbox
4. [ ] Control a light → **✓ Verify:** New log entries appear
5. [ ] Search for: `RELAY`
6. [ ] **✓ Verify:** Cloud relay messages highlighted

**Expected Result:** ✅ Logs accessible and functional

---

#### Test 5.3: Addon Control Buttons
**Steps:**
1. [ ] Click **"Restart"** button
2. [ ] **✓ Verify:** State changes to "Restarting" then "Running"
3. [ ] Wait 20 seconds
4. [ ] Test a light → **✓ Verify:** Still works after restart

**Expected Result:** ✅ Restart works, devices reconnect

---

### Category 6: Developer Tools (10 minutes)

#### Test 6.1: Entity State Inspection
**Steps:**
1. [ ] Navigate: Developer Tools → **States**
2. [ ] Filter for: `cync` or `hallway`
3. [ ] **✓ Verify:** All Cync devices appear
4. [ ] Click on a light entity → Check attributes:
   ```json
   {
     "brightness": 100,
     "color_mode": "color_temp",
     "color_temp": 5350,
     "supported_features": 43,
     "device_class": "light"
   }
   ```

**Expected Result:** ✅ All attributes present and accurate

---

#### Test 6.2: Service Call Test
**Steps:**
1. [ ] Navigate: Developer Tools → **Services**
2. [ ] Select service: **`light.turn_on`**
3. [ ] Select target: **Hallway Floodlight 3**
4. [ ] Set parameters (YAML):
   ```yaml
   brightness: 50
   color_temp: 3000
   ```
5. [ ] Click **"Call Service"**
6. [ ] **✓ Verify:** Light turns on at 50% brightness with 3000K color

**Expected Result:** ✅ Service call executes correctly

---

#### Test 6.3: MQTT Message Inspection
**Steps:**
1. [ ] Navigate: Developer Tools → **MQTT**
2. [ ] Subscribe to topic: `cync_lan_addon/#`
3. [ ] Toggle a light in GUI
4. [ ] **✓ Verify:** MQTT messages appear:
   ```
   Topic: cync_lan_addon/set/hallway_floodlight_1
   Payload: {"state": "ON", "brightness": 100}
   ```

**Expected Result:** ✅ MQTT messages published correctly

---

### Category 7: Stress Testing (5-10 minutes)

#### Test 7.1: Rapid Commands
**Steps:**
1. [ ] Select a light
2. [ ] Rapidly click ON/OFF 10 times (as fast as possible)
3. [ ] **✓ Verify:** All commands eventually process
4. [ ] **✓ Verify:** Final state matches GUI
5. [ ] Check logs → **✓ Verify:** No errors or timeouts

**Expected Result:** ✅ Handles rapid commands gracefully

---

#### Test 7.2: Multiple Simultaneous Commands
**Steps:**
1. [ ] Open 3-4 light entities in separate browser tabs
2. [ ] Simultaneously adjust all brightness sliders
3. [ ] **✓ Verify:** All devices respond
4. [ ] Check addon logs → **✓ Verify:** No errors

**Expected Result:** ✅ Concurrent commands handled

---

#### Test 7.3: Device Unavailable Handling
**Steps:**
1. [ ] Note a device that can be powered off
2. [ ] **Power off the device physically**
3. [ ] Wait 30-60 seconds
4. [ ] Refresh Home Assistant
5. [ ] **✓ Verify:** Entity shows **"Unavailable"** state
6. [ ] Try to control it → **✓ Verify:** Command fails gracefully
7. [ ] **Power device back on**
8. [ ] Wait 30 seconds
9. [ ] **✓ Verify:** Entity becomes available again

**Expected Result:** ✅ Unavailable states handled correctly

---

### Category 8: Performance Validation (5 minutes)

#### Test 8.1: Latency Measurement
**Steps:**
1. [ ] Select a light
2. [ ] Use stopwatch or count seconds
3. [ ] Click ON → Measure time until physical light turns on
4. [ ] Record: _____ seconds
5. [ ] Repeat 5 times, calculate average
6. [ ] **Expected:** < 2 seconds average

**Current Configuration:**
- Cloud Relay: **Enabled**
- Expected latency: **0.5-2 seconds**

**Expected Result:** ✅ Acceptable response time

---

## 📊 Results Summary Template

Fill out after testing:

| Category              | Tests  | Passed | Failed | Notes |
| --------------------- | ------ | ------ | ------ | ----- |
| Basic Light Controls  | 3      | __     | __     |       |
| Switch Controls       | 2      | __     | __     |       |
| Bidirectional Updates | 2      | __     | __     |       |
| Addon Config UI       | 2      | __     | __     |       |
| Addon Management UI   | 3      | __     | __     |       |
| Developer Tools       | 3      | __     | __     |       |
| Stress Testing        | 3      | __     | __     |       |
| Performance           | 1      | __     | __     |       |
| **TOTAL**             | **19** | __     | __     |       |

---

## 🐛 Issue Tracking

If any test fails, document here:

### Issue #1
- **Test:** [Test ID]
- **Observed:** [What happened]
- **Expected:** [What should happen]
- **Logs:** [Relevant log excerpts]
- **Severity:** Critical / High / Medium / Low

---

## 🎬 Automated Validation Scripts

After manual testing, run these commands to verify backend state:

```bash
# Check device count
ha addons logs local_cync-lan -n 200 | grep "Device endpoint" | wc -l

# Verify relay connections
ha addons logs local_cync-lan -n 200 | grep "RELAY mode" | tail -5

# Count MQTT publishes
ha addons logs local_cync-lan -n 500 | grep "device_status" | wc -l

# Check for errors
ha addons logs local_cync-lan -n 500 | grep -i "error" | wc -l
```

---

## ✅ Sign-Off

**Tester Name:** _______________
**Date Completed:** _______________
**Overall Result:** PASS / FAIL / PARTIAL
**Ready for Production:** YES / NO / WITH NOTES

**Notes:**
-
-
-

---

## 📸 Screenshots (Optional)

Recommended screenshots:
1. Light control panel showing brightness/color temp sliders
2. Addon configuration UI showing cloud_relay options
3. Developer Tools → States showing Cync entities
4. Addon logs showing relay activity
5. Entity unavailable state (if tested)

Save to: `/mnt/supervisor/addons/local/hass-addons/gui-test-screenshots/`

---

**Next Steps After GUI Testing:**
1. Update `CLOUD_RELAY_TEST_EXECUTION_RESULTS.md` with Phase 8 results
2. Document any issues found
3. Create follow-up tasks for fixes (if needed)
4. Sign off on production readiness

