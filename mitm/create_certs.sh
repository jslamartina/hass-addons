#!/bin/bash
# Create self-signed SSL certificates for Cync MITM debugging
# These certificates allow socat to intercept SSL/TLS traffic from Cync devices

set -e

CERTS_DIR="certs"
KEY_FILE="$CERTS_DIR/key.pem"
CERT_FILE="$CERTS_DIR/cert.pem"
SERVER_FILE="$CERTS_DIR/server.pem"

echo "========================================"
echo "  Cync MITM Certificate Generator"
echo "========================================"
echo ""

# Create certs directory if it doesn't exist
if [ ! -d "$CERTS_DIR" ]; then
  echo "Creating $CERTS_DIR directory..."
  mkdir -p "$CERTS_DIR"
fi

# Check if certificates already exist
if [ -f "$SERVER_FILE" ]; then
  echo "⚠️  Certificates already exist!"
  echo ""
  read -p "Do you want to regenerate them? (y/N): " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted. Using existing certificates."
    exit 0
  fi
  echo ""
fi

echo "Generating self-signed certificate..."
echo "Subject: CN=*.xlink.cn (wildcard for Cync domains)"
echo ""

# Generate private key and certificate
openssl req -x509 -newkey rsa:4096 \
  -keyout "$KEY_FILE" \
  -out "$CERT_FILE" \
  -days 365 \
  -nodes \
  -subj "/CN=*.xlink.cn" \
  2> /dev/null

# Combine key and cert for socat
cat "$KEY_FILE" "$CERT_FILE" > "$SERVER_FILE"

# Set secure permissions
chmod 600 "$KEY_FILE" "$SERVER_FILE"
chmod 644 "$CERT_FILE"

echo "✓ Certificates created successfully!"
echo ""
echo "Files created:"
echo "  - $KEY_FILE (private key)"
echo "  - $CERT_FILE (public certificate)"
echo "  - $SERVER_FILE (combined, for socat)"
echo ""
echo "Valid for: 365 days"
echo ""
echo "Next steps:"
echo "1. Set up DNS redirection (cm.gelighting.com → your IP)"
echo "2. Run: ./mitm_capture.sh"
echo ""
