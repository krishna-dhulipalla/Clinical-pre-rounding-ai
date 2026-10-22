FROM node:22.14-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY scripts/run_workbench.py ./scripts/run_workbench.py
COPY data ./data
COPY web/public ./web/public
COPY --from=web /web/dist ./web/dist
RUN uv sync --frozen --no-dev --no-editable && useradd --create-home --uid 10001 workbench && mkdir -p /app/.local && chown workbench:workbench /app/.local
ENV PATH="/app/.venv/bin:$PATH"
USER workbench
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
CMD ["python", "scripts/run_workbench.py", "serve", "--host", "0.0.0.0"]
