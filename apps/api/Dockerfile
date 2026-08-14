FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, database migrations, and tests
COPY apps/api/app/ ./app/
COPY db/ ./db/
COPY tests/ ./tests/

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
