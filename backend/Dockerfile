FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt
COPY backend /app/backend
COPY data /app/data
WORKDIR /app/backend
RUN chmod +x entrypoint.sh
EXPOSE 8000
CMD ["./entrypoint.sh"]

