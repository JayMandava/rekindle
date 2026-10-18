FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY rekindle ./rekindle
COPY sql ./sql
# Cloud Run injects PORT
CMD exec uvicorn rekindle.api:app_factory --factory --host 0.0.0.0 --port ${PORT:-8080}
