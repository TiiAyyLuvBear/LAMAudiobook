FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    espeak-ng \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY . /app/

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose API port
EXPOSE 8001

# Command can be overridden in docker-compose for worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
