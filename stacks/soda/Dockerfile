# =============================================================================
# Soda Core - ARM64-compatible build
# =============================================================================
# Official sodadata/soda-core image doesn't support ARM64, so we build our own
# using Python 3.11 base image and install soda-core via pip.
# =============================================================================

FROM python:3.11-slim

# Install system dependencies required by Soda Core
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Soda Core with PostgreSQL support
RUN pip install --no-cache-dir \
    soda-core-postgres==3.3.7

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Default command (sleep infinity for CLI access)
CMD ["sleep", "infinity"]
