# syntax=docker/dockerfile:1.7

FROM python:3.11-alpine
LABEL maintainer="support@taiga.io"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONFAULTHANDLER=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /taiga-back
COPY requirements.txt requirements-contribs.txt /tmp/pip/

RUN set -eux; \
    apk add --no-cache --virtual .build-deps \
       build-base git linux-headers musl-dev \
       postgresql-dev libffi-dev openssl-dev \
       jpeg-dev zlib-dev libxml2-dev libxslt-dev

RUN --mount=type=cache,target=/root/.cache/pip \
    set -eux; \
    python -m pip install --upgrade pip; \
    python -m pip install wheel; \
    python -m pip install -r /tmp/pip/requirements.txt; \
    python -m pip install -r /tmp/pip/requirements-contribs.txt

RUN set -eux; \
    apk del .build-deps; \
    rm -rf /tmp/pip

RUN set -eux; \
    apk add --no-cache \
       bash libpq su-exec

COPY . /taiga-back

RUN set -eux; \
    chmod +x docker/entrypoint.sh; \
    chmod +x docker/async_entrypoint.sh; \
    cp docker/config.py settings/config.py

RUN set -eux; \
    apk add --no-cache --virtual .i18n-deps gettext

RUN set -eux; \
    python manage.py compilemessages

RUN set -eux; \
    apk del .i18n-deps

RUN set -eux; \
    python manage.py collectstatic --no-input

RUN set -eux; \
    addgroup -S taiga; \
    adduser -S -D -H -G taiga -s /bin/bash taiga; \
    mkdir -p /taiga-back/media/exports; \
    chown -R taiga:taiga /taiga-back; \
    rm requirements.txt requirements-contribs.txt; \
    find . -name '__pycache__' -exec rm -r '{}' +; \
    find . -name '*pyc' -exec rm -r '{}' +; \
    find . -name '*po' -exec rm -r '{}' +

ENV DJANGO_SETTINGS_MODULE=settings.config
EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
