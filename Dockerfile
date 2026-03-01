FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for libarchive
RUN apt-get update && apt-get install -y \
    libarchive-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .
COPY start.py .
# Create necessary directories
RUN mkdir -p downloads logs

# Run the bot
CMD ["python", "start.py"]
