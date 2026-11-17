FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000 \
    SECUREPAPER_DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /app/backend
COPY frontend /app/frontend
COPY seed /app/seed
COPY data /app/data
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh && mkdir -p /app/data
EXPOSE 8000
VOLUME ["/app/data"]
CMD ["/app/start.sh"]
