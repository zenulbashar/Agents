# Foundry Support API. Build from the REPO ROOT so the service can import
# services.telegram and read config/support_api.yaml:
#   docker build -f services/support_api/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY services/support_api/requirements.txt /app/services/support_api/requirements.txt
RUN pip install --no-cache-dir -r /app/services/support_api/requirements.txt

COPY services/support_api /app/services/support_api
COPY services/telegram /app/services/telegram
COPY config/support_api.yaml /app/config/support_api.yaml
COPY config/telegram.yaml /app/config/telegram.yaml

EXPOSE 8100
CMD ["python3", "-m", "services.support_api.main"]
