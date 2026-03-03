# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install libarchive-dev system dependency
RUN apt-get update && apt-get install -y \
    libarchive-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python modules
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot script
COPY start.py .
COPY bot.py .
COPY app.py .
# Run the bot
CMD ["python", "start.py"]
