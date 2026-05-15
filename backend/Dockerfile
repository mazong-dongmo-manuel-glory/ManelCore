FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install Python deps — allow pip to resolve the openai version conflict
RUN pip install --no-cache-dir -r requirements.txt --upgrade

COPY . .

# Health endpoint on /health
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
