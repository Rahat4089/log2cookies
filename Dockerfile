FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    p7zip-full \
    unrar \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY bot.py .
COPY config.py .

# Create necessary directories
RUN mkdir -p downloads extracted results logs

# Run the bot
CMD ["python", "start.py"]
