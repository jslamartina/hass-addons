ARG BUILD_FROM
FROM $BUILD_FROM

ENV PYTHONUNBUFFERED=1
ENV PIP_BREAK_SYSTEM_PACKAGES=1

ARG BUILD_ARCH
ARG BUILD_VERSION
RUN set -x \
  && apk add --no-cache --no-interactive \
  openssl \
  nano \
  tree \
  && pip install --no-cache-dir -U pip \
  && pip install --no-cache-dir debugpy==1.8.0 \
  && mkdir -p /root/cync-lan/certs \
  && openssl req -x509 -newkey rsa:4096 \
  -keyout '/root/cync-lan/certs/key.pem' -out '/root/cync-lan/certs/cert.pem' \
  -subj '/CN=*.xlink.cn' -sha256 -days 3650 -nodes \
  && rm -rf /var/cache/apk/*

# Copy local cync-lan Python package source
COPY src/cync_lan /tmp/src/cync_lan
COPY pyproject.toml /tmp/pyproject.toml

ARG BUILD_ARCH
ARG BUILD_VERSION
RUN set -x \
  && pip install --no-cache-dir -U pip \
  && pip install --no-cache-dir /tmp \
  && rm -rf /tmp/src /tmp/pyproject.toml

ENV CYNC_HOST="0.0.0.0" \
  CYNC_DEBUG=1 \
  CYNC_RAW_DEBUG=1 \
  CYNC_TOPIC="cync_lan_addon" \
  CYNC_MQTT_PORT=1883 \
  CYNC_MQTT_HOST="homeassistant.local" \
  CYNC_MQTT_USER="" \
  CYNC_MQTT_PASS="" \
  CYNC_HASS_TOPIC="homeassistant" \
  CYNC_HASS_STATUS_TOPIC="status" \
  CYNC_HASS_BIRTH_MSG="online" \
  CYNC_HASS_WILL_MSG="offline" \
  CYNC_MQTT_CONN_DELAY=10 \
  CYNC_CMD_BROADCASTS=2 \
  CYNC_MAX_TCP_CONN=8 \
  CYNC_TCP_WHITELIST=""

# Copy data for add-on
COPY static/index.html /root/cync-lan/www/index.html

# Expose debug port for VS Code Python debugging
EXPOSE 5678
EXPOSE 23779
EXPOSE 23778

COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
