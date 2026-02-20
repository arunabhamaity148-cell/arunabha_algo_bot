FROM python:3.11-slim

# Install system dependencies including TA-Lib
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libta-lib0 \
    libta-lib-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "main:app", "--workers", "2", "--threads", "2", "--timeout", "120", "--bind", "0.0.0.0:8080"]
