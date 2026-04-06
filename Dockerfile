FROM python:3.11-alpine

WORKDIR /app

# Install dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot.py .
COPY .env.example .

# Health check - verify python process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "python bot.py" || exit 1

# Run bot
CMD ["python", "-u", "bot.py"]
