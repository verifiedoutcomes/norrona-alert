FROM python:3.12-slim

WORKDIR /app

# Install system deps for lxml and playwright
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/pyproject.toml backend/pyproject.toml
RUN pip install --no-cache-dir ./backend && \
    playwright install --with-deps chromium

# Copy backend source
COPY backend/ backend/

EXPOSE 8000

CMD ["uvicorn", "backend.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
