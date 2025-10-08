# SSL Certificates for MITM Debugging

This directory contains SSL certificates needed for MITM (Man-in-the-Middle) debugging of Cync devices.

## Generating Certificates

If the certificates don't exist, run the helper script from the parent directory:

```bash
cd /path/to/cync-lan-python
./create_certs.sh
```

Or manually:

```bash
openssl req -x509 -newkey rsa:4096 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes -subj "/CN=*.xlink.cn"
cat certs/key.pem certs/cert.pem > certs/server.pem
```

## Files

- `key.pem` - Private key
- `cert.pem` - Public certificate
- `server.pem` - Combined certificate (used by socat)

## Security Note

These certificates are for **local debugging only**. They are self-signed and should never be used in production. The `.gitignore` file prevents them from being committed to the repository.

