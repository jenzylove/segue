FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
# The Railway volume is attached after image build. Keep the mount point in
# the image as well so a first boot cannot fail if the volume is not attached;
# persistence still requires attaching the volume at /data in Railway.
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV SEGUE_DB_PATH=/data/segue_missions.sqlite3
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn backend.segue_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
