# =============================================================================
# GPT Researcher - built from a pinned release
# =============================================================================
# The published images (gptresearcher/gpt-researcher on Docker Hub,
# ghcr.io/assafelovic/gpt-researcher) stopped at 3.3.0 in 2025 and are amd64
# only. This builds the v3.7.0 release from its source archive on
# python:slim, for amd64 and arm64.
#
# Unlike upstream's Dockerfile it installs no Chromium or Firefox: the
# default scraper (BeautifulSoup) does not need a browser, and the browsers
# would add about a gigabyte.
# =============================================================================

FROM python:3.12.13-slim

ARG GPTR_VERSION=v3.7.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

RUN curl -fsSL "https://github.com/assafelovic/gpt-researcher/archive/refs/tags/${GPTR_VERSION}.tar.gz" \
      | tar -xz --strip-components=1 \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y build-essential && apt-get autoremove -y

RUN useradd --uid 1000 --create-home gpt-researcher \
    && mkdir -p /usr/src/app/outputs /usr/src/app/my-docs \
    && chown -R gpt-researcher:gpt-researcher /usr/src/app

USER gpt-researcher

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
