FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .

# La cache SQLite vive qui: montare un volume per non perderla tra i deploy.
ENV ODOO_STORE_DB_PATH=/srv/data/store.sqlite3
RUN mkdir -p /srv/data && useradd --create-home --uid 1000 api && chown -R api /srv
USER api

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
