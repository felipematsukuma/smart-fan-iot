FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.2 && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Executar via 'python -m uvicorn' resolve qualquer divergência de PATH
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]