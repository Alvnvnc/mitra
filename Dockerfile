# Mitra — single-process dashboard + agent runtime.
#
#   docker build -t mitra .
#   docker run --rm -p 8080:8080 -e MITRA_DEMO_MODE=1 -v mitra-data:/data mitra
#
# The image runs as an unprivileged user and keeps all state in /data so the
# container itself stays disposable.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# git is a runtime dependency of the digest skills (they scan the checkout);
# without it a run reports "repo scan unavailable" instead of real activity.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer first so source edits do not invalidate the install.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY scripts ./scripts
COPY docker/entrypoint.sh /usr/local/bin/mitra-entrypoint
RUN chmod +x /usr/local/bin/mitra-entrypoint \
    && useradd --create-home --uid 10001 mitra \
    && mkdir -p /data \
    && chown -R mitra:mitra /data /app

USER mitra

ENV MITRA_DATA_DIR=/data \
    MITRA_HOST=0.0.0.0 \
    MITRA_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/api/health', timeout=4).read()"

ENTRYPOINT ["mitra-entrypoint"]
CMD ["uvicorn", "mitra.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
