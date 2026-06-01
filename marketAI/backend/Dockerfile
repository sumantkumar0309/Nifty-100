FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-backend2.txt .
RUN pip install --no-cache-dir -r requirements-backend2.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs staticfiles media

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

CMD ["gunicorn", "backend2.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
