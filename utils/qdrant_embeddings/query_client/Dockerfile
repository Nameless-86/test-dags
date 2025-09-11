FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install git (needed by some HF models); clean up afterwards
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN uv pip install --no-cache-dir --upgrade pip --system && \
    uv pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt --system

# Copy the application code
COPY . /app
COPY local_e5_model/ /app/local_e5_model/

EXPOSE 8000
CMD ["uvicorn", "server:app","--host", "0.0.0.0", "--port", "8000","--log-level", "info", "--access-log"]
