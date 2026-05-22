FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    MLOPS_STORAGE_DIR=/mlops-storage

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install "setuptools==68.2.2" "wheel==0.41.2" \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/artifacts /app/logs /mlops-storage

EXPOSE 8000

CMD ["python", "-m", "madewithml.serve", "--backend", "fastapi"]
