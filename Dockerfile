# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (simplified and working versions)
RUN apt-get update && apt-get install -y \
    libarchive-dev \
    p7zip-full \
    unzip \
    gunicorn \
    flask \
    wget \
    curl \
    git \
    gcc \
    g++ \
    make \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install unrar from non-free repository
RUN apt-get update && apt-get install -y \
    unrar \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages in layers for better caching
RUN pip install --no-cache-dir --upgrade pip

# Install core packages
RUN pip install --no-cache-dir \
     pyrofork \
    tgcrypto

# Install async packages
RUN pip install --no-cache-dir \
    aiohttp \
    aiofiles

# Install utility packages
RUN pip install --no-cache-dir \
    tqdm \
    colorama \
    psutil

# Install extraction packages (without libarchive-c which causes issues)
RUN pip install --no-cache-dir \
    patool \
    pyunpack \
    rarfile \
    py7zr \
    zipfile36

# Create necessary directories
RUN mkdir -p /app/downloads /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV TZ=UTC

# Create a non-root user to run the bot
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Copy bot script
COPY --chown=botuser:botuser bot.py .

# Create volume for persistent data
VOLUME ["/app/downloads", "/app/logs"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; exit(0) if os.path.exists('/app/bot.py') else exit(1)"

# Run the bot
CMD ["python", "start.py"]
