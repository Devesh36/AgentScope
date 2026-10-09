FROM node:24-alpine AS build
WORKDIR /app/apps/web
COPY apps/web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM node:24-alpine
WORKDIR /app/apps/web
COPY --from=build /app/apps/web/.next/standalone ./
COPY --from=build /app/apps/web/.next/static ./.next/static
ENV HOSTNAME=0.0.0.0 PORT=3000 NEXT_TELEMETRY_DISABLED=1
CMD ["node", "server.js"]
