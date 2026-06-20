FROM ghcr.io/home-assistant/base-python:3.13-alpine3.24

ARG BUILD_VERSION=dev
ARG BUILD_ARCH=unknown

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.title="Home Assistant App: NeoHub Control" \
    org.opencontainers.image.description="Expose Heatmiser NeoHub devices to Home Assistant via MQTT Discovery." \
    org.opencontainers.image.source="https://github.com/GitDakky/NeoHub-Control" \
    org.opencontainers.image.licenses="MIT"

WORKDIR /opt/neohub-control
COPY requirements.txt /tmp/neohub-addon-requirements.txt
RUN python3 -m venv /opt/neohub-control/venv \
    && /opt/neohub-control/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/neohub-control/venv/bin/pip install --no-cache-dir -r /tmp/neohub-addon-requirements.txt

COPY app/ /opt/neohub-control/
COPY rootfs/ /

RUN chmod a+x /etc/services.d/neohub-control/run
