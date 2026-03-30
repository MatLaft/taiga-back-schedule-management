FROM python:3.11-alpine
LABEL maintainer="support@taiga.io"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONFAULTHANDLER=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . /taiga-back
WORKDIR /taiga-back

RUN set -eux; \
    apk add --no-cache \
       bash gettext libpq net-tools procps su-exec; \
    apk add --no-cache --virtual .build-deps \
       build-base git linux-headers musl-dev \
       postgresql-dev libffi-dev openssl-dev \
       jpeg-dev zlib-dev libxml2-dev libxslt-dev; \
    python -m pip install --upgrade pip; \
    python -m pip install wheel; \
    python -m pip install -r requirements.txt; \
    python -m pip install -r requirements-contribs.txt; \
    python -m pip install "networkx>=3.0"; \
    python manage.py compilemessages; \
    python manage.py collectstatic --no-input; \
    chmod +x docker/entrypoint.sh; \
    chmod +x docker/async_entrypoint.sh; \
    cp docker/config.py settings/config.py; \
    addgroup -S taiga; \
    adduser -S -D -H -G taiga -s /bin/bash taiga; \
    mkdir -p /taiga-back/media/exports; \
    chown -R taiga:taiga /taiga-back; \
    apk del .build-deps; \
    rm -rf /root/.cache; \
    rm requirements.txt requirements-contribs.txt; \
    find . -name '__pycache__' -exec rm -r '{}' +; \
    find . -name '*pyc' -exec rm -r '{}' +; \
    find . -name '*po' -exec rm -r '{}' +

ENV DJANGO_SETTINGS_MODULE=settings.config
EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
