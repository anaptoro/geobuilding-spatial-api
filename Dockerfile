FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y \
        gcc \
        g++ \
        libgeos-dev \
        libproj-dev \
        proj-data \
        proj-bin \
        libgdal-dev \
        gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY spatial_api/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY spatial_api /app/spatial_api

RUN mkdir -p /app/results

CMD ["uvicorn", "spatial_api.main:app", "--host", "0.0.0.0", "--port", "8001"]