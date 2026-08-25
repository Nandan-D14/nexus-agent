FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY nexus/ nexus/
RUN pip install --no-cache-dir --root-user-action=ignore .
CMD ["sh", "-c", "uvicorn nexus.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
