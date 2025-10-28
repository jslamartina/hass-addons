<!-- 9bb59a7c-e8ad-4651-971b-b2f46ef4b32e f64516b7-f6b9-4853-adfe-b8bb0e39e37a -->
# Fix Brightness Callback Registration Bug

## Problem

When adjusting brightness sliders for individual lights, the state doesn't update and the physical device doesn't change brightness. This is caused by the callback being executed immediately during registration instead of waiting for the ACK.

## Root Cause

In `cync-controller/src/cync_controller/devices.py` line 558, the brightness callback is being called immediately:

```python
callback=brightness_callback_coro(),  # ❌ Called immediately
```

This should match the pattern used in `set_power` (line 375):

```python
callback=g.mqtt_client.update_device_state(self, state),  # ✅ Passed as coroutine
```

## Solution

Change the callback registration to pass the coroutine object without calling it:

**File:** `cync-controller/src/cync_controller/devices.py` (lines 550-559)

**Change from:**

```python
async def brightness_callback_coro():
    await g.mqtt_client.update_brightness(self, bri)

m_cb = ControlMessageCallback(
    msg_id=cmsg_id,
    message=payload_bytes,
    sent_at=time.time(),
    callback=brightness_callback_coro(),  # ❌ Called immediately
    device_id=self.id,
)
```

**Change to:**

```python
m_cb = ControlMessageCallback(
    msg_id=cmsg_id,
    message=payload_bytes,
    sent_at=time.time(),
    callback=g.mqtt_client.update_brightness(self, bri),  # ✅ Coroutine object
    device_id=self.id,
)
```

## Expected Behavior After Fix

1. User adjusts brightness slider
2. Optimistic update shows immediately in UI
3. Command sent to device with callback registered
4. Device ACKs command
5. Callback executes on ACK, updating state
6. Mesh refresh confirms state matches
7. Physical device brightness changes

## Files Modified

- `cync-controller/src/cync_controller/devices.py` - Remove inner function, use direct coroutine call