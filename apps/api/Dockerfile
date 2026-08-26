FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system zhituo && useradd --system --gid zhituo --home-dir /app zhituo \
    && python -m pip install --no-cache-dir 'uv>=0.8,<1'

COPY pyproject.toml uv.lock ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN uv sync --locked --no-dev --no-editable \
    && /app/.venv/bin/python -c "from importlib.resources import files; from app.seed import DATA_FILE; DATA_FILE.parent.mkdir(parents=True, exist_ok=True); DATA_FILE.write_bytes(files('app').joinpath('demo_data/opportunities.json').read_bytes()); assert DATA_FILE.is_file()" \
    && /app/.venv/bin/python -m compileall -q app

USER zhituo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3).read()" || exit 1

# Uvicorn keeps its safe default forwarded-allow-ips=127.0.0.1. Deployments behind a
# remote proxy must explicitly configure trusted proxy addresses rather than trusting '*'.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
