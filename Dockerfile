FROM python:3.13.0-slim

LABEL maintainer="Komal Thareja <komal.thareja@gmail.com>"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# OS deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends cron curl && \
    rm -rf /var/lib/apt/lists/*

# 1) Install Python deps first (cache-friendly)
COPY requirements.txt /usr/src/app/requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# 2) Copy project and install package
COPY archiver /usr/src/app/archiver
COPY pyproject.toml README.md LICENSE /usr/src/app/
RUN python -m pip install --no-cache-dir /usr/src/app

# 3) Create non-root user
RUN groupadd --gid 1000 archiver && \
    useradd --uid 1000 --gid archiver --shell /bin/bash archiver && \
    mkdir -p /var/log/archiver && \
    chown -R archiver:archiver /usr/src/app /var/log/archiver

# 4) Entrypoint
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER archiver

EXPOSE 3500

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:3500/ps/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["archiver"]
