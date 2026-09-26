FROM node:22-bookworm-slim AS ui
WORKDIR /app
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package.json
RUN npm ci
COPY frontend frontend
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml requirements.lock.txt ./
COPY backend backend
COPY benchmark benchmark
COPY scripts scripts
COPY examples examples
# Editable install: the app resolves ROOT from its own location, so it must stay under /app (a site-packages copy
# would look for frontend/dist, examples/ and a writable .astflow/ inside site-packages).
RUN python -m pip install --no-cache-dir -c requirements.lock.txt -e . && useradd --create-home astflow && chown -R astflow:astflow /app
COPY --from=ui /app/frontend/dist frontend/dist
USER astflow
ENV ASTFLOW_SEMANTIC=off ASTFLOW_TS_ENRICH=false
EXPOSE 8000
CMD ["python", "scripts/container_start.py"]
