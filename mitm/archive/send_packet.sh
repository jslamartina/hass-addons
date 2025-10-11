#!/bin/bash
# Send a crafted 0x73 mode packet to a device via raw bytes

if [ "$#" -ne 2 ]; then
    echo "Usage: ./send_packet.sh <device_ip> <mode>"
    echo "  mode: 'smart' or 'traditional'"
    exit 1
fi

DEVICE_IP="$1"
MODE="$2"

# Endpoint for switch (from captures)
ENDPOINT="1b dc da 3e"

# Mode byte
if [ "$MODE" = "smart" ]; then
    MODE_BYTE="b0"
elif [ "$MODE" = "traditional" ]; then
    MODE_BYTE="50"
else
    echo "Invalid mode: $MODE"
    exit 1
fi

# Counter (start with 0x00)
COUNTER="00"

# Build packet (43 bytes)
# Header (5) + Endpoint (7) + Start marker + command (5) + subcommand (3) + unknown (2) + unknown (2) + IDs (4) + unknown (3) + mode bytes (3) + padding (6) + unknown (1) + checksum (1) + end marker (1)

# Craft the packet hex string
PACKET="73 00 00 00 26 ${ENDPOINT} 01 ${COUNTER} 00 7e 23 01 00 00 fa 8e 14 00 73 04 00 a0 00 4c 00 ea 11 02 a0 81 ${MODE_BYTE} 00 00 00 00 00 00 14 XX 7e"

echo "Packet template: $PACKET"
echo ""
echo "Calculating checksum..."

# For now, let's just use the checksums from our captures
# Smart mode (0xb0): checksum is 0xf2
# Traditional mode (0x50): checksum is 0x87

if [ "$MODE" = "smart" ]; then
    CHECKSUM="f2"
else
    CHECKSUM="87"
fi

PACKET=$(echo "$PACKET" | sed "s/XX/$CHECKSUM/")

echo "Final packet: $PACKET"
echo ""
echo "This script requires manual injection via socat or netcat"
echo "Alternatively, we should restart the MITM and manually inject when device connects"

