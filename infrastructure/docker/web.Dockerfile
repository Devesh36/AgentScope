# syntax=docker/dockerfile:1
FROM node:24.14.0-bookworm-slim@sha256:d8e448a56fc63242f70026718378bd4b00f8c82e78d20eefb199224a4d8e33d8 AS build
WORKDIR /app/apps/web
COPY apps/web/package*.json ./
RUN --mount=type=secret,id=proxy_ca,required=true \
    NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca npm ci --strict-ssl=true --no-audit --no-fund
COPY apps/web ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM node:24.14.0-bookworm-slim@sha256:d8e448a56fc63242f70026718378bd4b00f8c82e78d20eefb199224a4d8e33d8
WORKDIR /app/apps/web
RUN groupadd --gid 10001 agentscope && useradd --uid 10001 --gid 10001 --no-create-home agentscope
COPY --from=build --chown=10001:10001 --chmod=755 /app/apps/web/.next/standalone ./
COPY --from=build --chown=10001:10001 --chmod=755 /app/apps/web/.next/static ./.next/static
COPY --chown=10001:10001 --chmod=755 infrastructure/docker/web_*.mjs /app/
ENV HOSTNAME=0.0.0.0 PORT=3000 NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production AGENTSCOPE_CONTAINER=1
USER 10001:10001
ENTRYPOINT ["node", "/app/web_start.mjs"]
