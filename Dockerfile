FROM python:3.12-slim

# Debian's ffmpeg includes libass (subtitles) and zimg (HDR tonemapping).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

# The library is a Cloud Storage bucket mounted at /library; the index and outputs are per-instance.
ENV PATH=/app/.venv/bin:$PATH \
    FILMSPOTTING_LIBRARY_DIR=/library \
    FILMSPOTTING_DATA_DIR=/tmp/data
CMD ["sh", "-c", "filmspotting scan && exec filmspotting serve --host 0.0.0.0 --port ${PORT:-8080}"]
