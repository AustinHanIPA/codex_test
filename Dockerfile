FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY crypto_monitor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY crypto_monitor /app/crypto_monitor

WORKDIR /app/crypto_monitor

EXPOSE 28593

CMD ["python", "main.py"]
