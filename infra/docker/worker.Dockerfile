FROM python:3.12-slim
WORKDIR /app
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install-deps chromium && python -m cloakbrowser install
COPY services/api/ .
ENV PYTHONPATH=/app
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=INFO", "--queues=critical,high,normal,low", "--concurrency=1"]
