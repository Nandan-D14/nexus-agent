FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --root-user-action=ignore uv

# Install the exact, hash-pinned dependency set from uv.lock (cached layer that
# only rebuilds when dependencies change), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv export --locked --no-dev --no-emit-project --format requirements-txt -o /tmp/requirements.txt \
    && pip install --no-cache-dir --root-user-action=ignore -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
COPY nexus/ nexus/
RUN pip install --no-cache-dir --root-user-action=ignore --no-deps .

RUN useradd --create-home --uid 10001 app
USER app

CMD ["sh", "-c", "uvicorn nexus.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-graceful-shutdown 8"]
