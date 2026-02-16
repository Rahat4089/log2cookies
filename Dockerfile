# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    TZ=UTC

# Install system dependencies including archive tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Archive tools
    p7zip-full \
    unrar \
    unzip \
    tar \
    gzip \
    bzip2 \
    xz-utils \
    # System utilities
    procps \
    curl \
    wget \
    # Build tools (if needed)
    gcc \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /app/downloads /app/extracted /app/results /app/temp

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user to run the application
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Create volume mounts for persistent data
VOLUME ["/app/downloads", "/app/extracted", "/app/results", "/app/temp"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; exit(0) if os.path.exists('/app/bot.pid') else exit(1)" || exit 1

# Run the bot
CMD ["python", "start.py"]
