ARG BUILD_FROM=ghcr.io/home-assistant/base:3.24
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    DAC_DATA=/data \
    DAC_HOST=0.0.0.0 \
    DAC_PORT=8099 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apk add --no-cache \
        python3 \
        py3-pip \
        jq

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY app /app/app
COPY run.sh /run.sh
RUN chmod +x /run.sh

LABEL \
    io.hass.name="DAC – Dynamic Alarm Clock" \
    io.hass.description="Dynamischer Wecker mit Echo-Wecker, Licht und Urlaubskalender" \
    io.hass.type="app" \
    io.hass.version="1.0.0" \
    io.hass.arch="aarch64|amd64|armv7|armhf"

CMD [ "/run.sh" ]
