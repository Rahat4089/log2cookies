# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including libarchive and 7zip
RUN apt-get update && apt-get install -y \
    libarchive-dev \
    libarchive-tools \
    p7zip-full \
    unrar \
    unzip \
    wget \
    curl \
    git \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    pyrofork \
    tgcrypto \
    aiohttp \
    aiofiles \
    tqdm \
    colorama \
    psutil \
    patool \
    pyunpack \
    libarchive-c \
    python-magic \
    python-magic-bin \
    rarfile \
    py7zr

# Create necessary directories
RUN mkdir -p /app/downloads /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

# Create a non-root user to run the bot
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Copy bot script
COPY bot.py .

# Create volume for persistent data
VOLUME ["/app/downloads", "/app/logs"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; exit(0) if os.path.exists('/app/bot.py') else exit(1)"

# Run the bot
CMD ["python", "start.py"]
