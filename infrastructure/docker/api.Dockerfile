# syntax=docker/dockerfile:1
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app/apps/api
WORKDIR /app
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN --mount=type=secret,id=proxy_ca,required=true \
    PIP_CERT=/run/secrets/proxy_ca pip install --require-hashes --no-cache-dir -r apps/api/requirements.txt
RUN groupadd --gid 10001 agentscope && useradd --uid 10001 --gid 10001 --no-create-home agentscope
COPY --chown=10001:10001 --chmod=755 apps/api apps/api
COPY --chown=10001:10001 --chmod=755 infrastructure/docker/api_*.py infrastructure/docker/
ENV AGENTSCOPE_CONTAINER=1 AGENTSCOPE_DATA_DIR=/tmp/agentscope
USER 10001:10001
WORKDIR /app/apps/api
ENTRYPOINT ["python", "/app/infrastructure/docker/api_start.py"]
