FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/mihail-pop/world-journal"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["python", "-m", "waitress", "--listen=0.0.0.0:8000", "--threads=8", "config.wsgi:application"]