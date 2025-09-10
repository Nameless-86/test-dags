FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY qdrant_embeddings/requirements.txt .
COPY qdrant_embeddings/*.py .
COPY ../vector/*.json vector/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt


RUN mkdir -p /app/qdrant_storage

ENV PYTHONUNBUFFERED=1
ENV QDRANT_URL=http://qdrant:6333

# Comando de inicio
CMD ["python", "main.py"]
