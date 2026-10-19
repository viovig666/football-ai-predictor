FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose port
EXPOSE 8080

# Run
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
