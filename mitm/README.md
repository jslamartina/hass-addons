# ⚠️⚠️⚠️ SECURITY WARNING ⚠️⚠️⚠️

## DEBUG TOOLS ONLY - DO NOT USE IN PRODUCTION

This directory contains **Man-in-the-Middle (MITM) debugging tools** that are designed for local development and protocol analysis only.

### ⚠️ CRITICAL SECURITY RISKS

These tools:
- **Disable ALL SSL/TLS certificate verification**
- **Make you vulnerable to man-in-the-middle attacks**
- **Should NEVER be used on untrusted networks**
- **Should NEVER be used in production environments**

### 🎯 Intended Use

These tools are designed for:
- Local debugging of Cync device communication
- Protocol analysis and reverse engineering
- Development and testing in controlled environments

### 🚫 What NOT to do

- ❌ Run these on public networks
- ❌ Use in production environments
- ❌ Trust these tools for secure communication
- ❌ Share these tools without security warnings

### 🔒 Security Best Practices

1. **Only use on isolated local networks**
2. **Never run on production systems**
3. **Always review code before execution**
4. **Consider these tools as permanently compromised for security purposes**

### 📁 Files in this directory

- `mitm_with_injection.py` - Main MITM proxy with packet injection
- `query_mode.py` - Device mode query tool
- `send_via_mitm.py` - Mode change packet sender
- `packet_parser.py` - Protocol packet parser
- `*.sh` - Various shell scripts for MITM setup

### 🛡️ For Production Use

Use the main CyncLAN add-on in the parent directory for secure, production-ready device control.

---

**Remember: These are debugging tools, not production code!**