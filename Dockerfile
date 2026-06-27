FROM python:3.10-slim

# Set up the working directory
WORKDIR /app

# Copy dependencies first for better caching
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Run the agent in the foreground, using the in-app scheduler (fallback loop)
# The OS-level cron is not needed in Docker, we just leave it running
CMD ["python", "news_agent.py"]
