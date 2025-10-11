# MITM Directory Cleanup - October 11, 2025

## Summary

Cleaned up the `mitm/` directory by archiving historical files and removing redundant documentation.

## Changes Made

### 📚 Documentation
- **Archived:** `TESTING_PLAN.md` - Original test plan (superseded by MITM_TESTING_GUIDE.md)
- **Streamlined:** `MITM_TESTING_GUIDE.md` reduced from 590 to 494 lines by removing protocol details that are better covered in FINDINGS_SUMMARY.md

### 🔧 Scripts Archived (Historical)
- `checksum_analysis.py` - Original checksum reverse engineering
- `verify_checksum.py` - Checksum verification tool
- `query_current_mode.sh` - Simple instruction printer
- `capture_status_comparison.sh` - Historical capture comparison
- `send_packet.sh` - Direct packet sender (superseded by inject_mode.sh)
- `mitm_capture.sh` - Socat-based capture (superseded by mitm_with_injection.py)

### 📄 Capture Files Archived
- `clean_capture_test.txt`
- `config_change_capture.txt`
- `mode_change_bt_off.txt`
- `mode_comparison.txt`
- `mode_test_capture.txt`
- `smart_bulb_mode_test.txt`
- `smart_mode_capture.txt`
- `switch_config_test.txt`

**Kept (referenced in docs):**
- `smart_to_traditional.txt` - Referenced in mode_change_analysis.md
- `traditional_to_smart.txt` - Referenced in mode_change_analysis.md

### 📊 Log Files Archived
- `mitm_test.log` (Oct 7)
- `mode_test_capture.log` (Oct 8)
- `status_comparison_*.log` (Oct 7-8)

**Kept (current):**
- `mitm.log` - Active MITM log
- `mitm_proxy.log` - Active proxy log

### 🗑️ Deleted (Empty Files)
- `switch_config_capture.txt`
- `traditional_mode_capture_new.txt`
- `test_run.txt`

## Current Active Files

### Documentation (4 files)
- `README.md` - Security warnings and overview
- `MITM_TESTING_GUIDE.md` - Practical operations guide
- `FINDINGS_SUMMARY.md` - Complete protocol analysis
- `mode_change_analysis.md` - Captured packet examples

### Core Tools (5 files)
- `mitm_with_injection.py` - Main MITM proxy with injection
- `packet_parser.py` - Protocol parser
- `checksum.py` - Checksum calculation
- `query_mode.py` - Mode query tool
- `test_mode_change.py` - Mode change testing
- `send_via_mitm.py` - Packet sender via MITM

### Helper Scripts (5 files)
- `create_certs.sh` - SSL certificate generation
- `inject_mode.sh` - Mode injection helper
- `inject_raw.sh` - Raw packet injection
- `run_mitm.sh` - MITM startup script
- `restart_mitm.sh` - MITM restart utility

### Support Files
- `pyproject.toml` - Project metadata
- `certs/` - SSL certificates directory

## Archive Location

All historical files are preserved in `archive/` directory with a README explaining their purpose.

## Impact

- **Reduced clutter:** 23 files archived
- **Clearer structure:** Active vs historical files separated
- **Better maintainability:** Current documentation doesn't duplicate protocol details
- **No data loss:** All historical files preserved for reference

## Document Roles (Post-Cleanup)

| Document | Purpose |
|----------|---------|
| **README.md** | Security warnings, file overview |
| **MITM_TESTING_GUIDE.md** | Practical "how-to" guide |
| **FINDINGS_SUMMARY.md** | Complete protocol reference |
| **mode_change_analysis.md** | Packet capture examples |
| **TESTING_PLAN.md** | Historical test plan (archived) |
