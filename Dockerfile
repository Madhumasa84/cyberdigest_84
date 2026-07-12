FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CYBERDIGEST_HEADLESS=1 \
    CYBERDIGEST_DATA_DIR=/data

# System deps for optional tray libs are not needed in headless image
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY news_agent.py .
COPY cyberdigest/ ./cyberdigest/
COPY config.example.json .
COPY feeds.yaml .
COPY config.json .

# Runtime data lives on a volume
RUN mkdir -p /data/reports \
    && if [ ! -f /app/config.json ]; then cp /app/config.example.json /app/config.json; fi

VOLUME ["/data"]

CMD ["python", "news_agent.py", "--cli-only"]
