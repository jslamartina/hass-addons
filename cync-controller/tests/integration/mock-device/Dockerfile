FROM python:3.13-alpine

# Install basic utilities
RUN apk add --no-cache --no-interactive netcat-openbsd

# Set working directory
WORKDIR /app

# Copy mock device script
COPY mock_cync_device.py /app/
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run mock device
CMD ["python", "-u", "mock_cync_device.py"]
