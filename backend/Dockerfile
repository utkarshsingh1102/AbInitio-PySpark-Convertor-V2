FROM python:3.11-slim

WORKDIR /app

# Java for PySpark + ksh + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless ksh curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/backend
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
