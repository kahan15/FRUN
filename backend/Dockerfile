FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.lock .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.lock

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.lock .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.lock \
    && rm -rf /wheels && useradd --create-home --uid 10001 runner
COPY --chown=runner:runner app ./app
COPY --chown=runner:runner migrations ./migrations
COPY --chown=runner:runner ops ./ops
COPY --chown=runner:runner alembic.ini .
USER runner
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log", "--limit-concurrency", "32", "--timeout-keep-alive", "5", "--timeout-graceful-shutdown", "30"]

FROM runtime AS test
USER root
COPY requirements-dev.lock .
RUN pip install --no-cache-dir -r requirements-dev.lock
COPY --chown=runner:runner tests ./tests
COPY --chown=runner:runner pyproject.toml .
USER runner
CMD ["python", "-m", "pytest", "-q", "-o", "cache_dir=/tmp/pytest-cache"]
