FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CYBERDIGEST_HEADLESS=1 \
    CYBERDIGEST_DATA_DIR=/data \
    CYBERDIGEST_CONFIG_DIR=/app

# Install pinned dependencies in a cacheable layer, then install the package.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

COPY news_agent.py .
COPY config.example.json .
COPY feeds.yaml .
COPY config.json .

# Runtime data lives on a volume
RUN mkdir -p /data/reports

VOLUME ["/data"]

CMD ["python", "-m", "cyberdigest", "--cli-only"]
