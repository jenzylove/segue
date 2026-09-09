FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend

ENV PYTHONUNBUFFERED=1
ENV SEGUE_DB_PATH=/data/segue_missions.sqlite3
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn backend.segue_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
