# AAMS-X backend.
#
# Two stages so the runtime image carries no build toolchain. The data cache is a
# mounted volume, not a layer: 139 MB of public recordings belong on the host, and
# baking them in would make the image unreproducible the day the archive rotates.

FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# scipy/pyarrow ship manylinux wheels; gcc is here only for a source-only fallback.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the metadata first so the dependency layer survives source edits.
COPY pyproject.toml README.md ./
COPY aamsx/version.py aamsx/version.py
RUN pip install --upgrade pip && pip install .

COPY aamsx aamsx
RUN pip install --no-deps .


FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AAMSX_DATA_DIR=/data \
    AAMSX_REPORTS_DIR=/data/reports

COPY --from=build /opt/venv /opt/venv

# Unprivileged by default: the service reads a cache and writes reports, and needs
# nothing else.
RUN useradd --create-home --uid 10001 aamsx \
 && mkdir -p /data/reports \
 && chown -R aamsx:aamsx /data

WORKDIR /app
COPY --chown=aamsx:aamsx aamsx aamsx
COPY --chown=aamsx:aamsx scripts scripts
COPY --chown=aamsx:aamsx pyproject.toml README.md ./

USER aamsx
EXPOSE 8000

# /api/health never touches disk, so the container reports healthy while a cache
# build is still running — which is the state you want to be able to observe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "aamsx.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
