# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --without dev

FROM python:3.11-slim AS runtime
WORKDIR /app

# Security: run as non-root
RUN groupadd -r cge && useradd -r -g cge cge
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY cge/ ./cge/

USER cge
EXPOSE 8000
ENTRYPOINT ["uvicorn", "cge.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
