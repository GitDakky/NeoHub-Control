ARG BUILD_FROM=ghcr.io/hassio-addons/base:15.0.8
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apk add --no-cache python3 py3-pip

WORKDIR /opt/neohub-control
COPY requirements.txt /tmp/neohub-addon-requirements.txt
RUN python3 -m venv /opt/neohub-control/venv \
    && /opt/neohub-control/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/neohub-control/venv/bin/pip install --no-cache-dir -r /tmp/neohub-addon-requirements.txt

COPY app/ /opt/neohub-control/
COPY rootfs/ /

RUN chmod a+x /etc/services.d/neohub-control/run
