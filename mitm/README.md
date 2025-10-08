# MITM Debugging Tools for Cync Devices

This directory contains tools for intercepting and analyzing traffic between Cync devices and the Cync cloud servers. This is useful for reverse engineering device behavior and discovering new protocol features.

## 📁 Contents

- `create_certs.sh` - Generate self-signed SSL certificates for MITM
- `mitm_capture.sh` - Run socat MITM proxy and capture traffic
- `certs/` - SSL certificates directory (gitignored)

## 🚀 Quick Start

### 1. Generate Certificates (First Time Only)

```bash
cd mitm
./create_certs.sh
```

This creates:
- `certs/key.pem` - Private key
- `certs/cert.pem` - Public certificate
- `certs/server.pem` - Combined certificate for socat

### 2. Set Up DNS Redirection

Configure your DNS server (AdGuard Home, Unbound, or router) to redirect these domains to your machine:

- `cm.gelighting.com` → Your machine IP
- `cm-sec.gelighting.com` → Your machine IP
- `cm-ge.xlink.cn` → Your machine IP

### 3. Run MITM Capture

```bash
./mitm_capture.sh my_capture_session.txt
```

**Important**: Turn OFF Bluetooth on your phone to force HTTP/TCP communication!

### 4. Test with Cync App

1. Open Cync mobile app
2. Navigate to device settings
3. Toggle **ONE** setting at a time
4. Wait 10 seconds
5. Press `Ctrl+C` to stop capture

### 5. Analyze Results

```bash
# View entire capture
cat my_capture_session.txt

# View device → cloud traffic
grep '>' my_capture_session.txt

# View cloud → device traffic
grep '<' my_capture_session.txt
```

## 📊 Understanding the Logs

- `>` = Traffic from device/app to cloud
- `<` = Traffic from cloud to device/app
- Hex values show the raw packet data
- Compare with `cync-lan/docs/packet_structure.md` for known packet types

## 🎯 Best Practices

1. **One change per capture** - Only modify one setting per session for clean logs
2. **Descriptive filenames** - Name captures after what you're testing:
   - `switch_smart_bulb_mode_enable.txt`
   - `dimmer_fade_rate_change.txt`
   - `motion_sensor_timeout_adjust.txt`
3. **Take notes** - Document what you changed and when
4. **Compare before/after** - Capture baseline, make change, capture again

## 🔍 What to Look For

When reverse engineering configuration commands:

- New packet types not in `packet_structure.md`
- Different data patterns in known packet types
- Sequence of packets when making config changes
- Response codes from the cloud server
- Differences between control vs configuration packets

## 🛠️ Troubleshooting

**No traffic captured?**
- Verify DNS redirection is working (`nslookup cm.gelighting.com`)
- Ensure Bluetooth is OFF on your phone
- Check firewall isn't blocking port 23779
- Try power cycling the Cync device

**Certificate errors?**
- Regenerate certificates: `./create_certs.sh`
- Ensure `certs/server.pem` exists and is readable

**socat not found?**
- Install: `sudo apt-get install socat` (Debian/Ubuntu)

## 🔐 Security Note

These tools are for **local debugging only**. The self-signed certificates should never be used in production. All certificate files are gitignored to prevent accidental commits.

## 📚 Related Documentation

- [Cync Packet Structure](../cync-lan/cync-lan-python/docs/packet_structure.md)
- [Debugging Setup Guide](../cync-lan/cync-lan-python/docs/debugging_setup.md)
- [Known Devices](../cync-lan/cync-lan-python/docs/known_devices.md)

