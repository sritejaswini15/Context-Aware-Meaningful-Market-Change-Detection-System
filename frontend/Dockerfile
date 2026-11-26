FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Rewrites are resolved at build time. In AWS the load balancer routes /api/* to
# the API directly, so this only matters for docker-compose / single-host setups.
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S knoww && adduser -S knoww -G knoww
COPY --from=build --chown=knoww:knoww /app/.next/standalone ./
COPY --from=build --chown=knoww:knoww /app/.next/static ./.next/static
COPY --from=build --chown=knoww:knoww /app/public ./public
USER knoww
EXPOSE 3000
CMD ["node", "server.js"]
