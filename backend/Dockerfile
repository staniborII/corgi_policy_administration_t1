# ---- Build stage ----
FROM python:3.12.12-slim AS builder

RUN pip install --no-cache-dir uv==0.9.27

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# ---- Runtime stage ----
FROM python:3.12.12-slim AS runtime

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --no-create-home appuser

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/ /app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

RUN python manage.py collectstatic --noinput 2>/dev/null || true

USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
