FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY app.py .
COPY templates templates
COPY static static
USER app
EXPOSE 8000
CMD ["sh", "-c", "flask --app app init-db && exec gunicorn --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile - app:app"]
