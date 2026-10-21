# Vyuh on a Hugging Face Docker Space (D38): the built web app and the FastAPI backend in one container.
#   docker build -t vyuh . && docker run -p 7860:7860 --env-file .env vyuh     # http://localhost:7860

# 1. Build the web app.
FROM node:22.20.0-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY web/ ./
RUN npm run build

# 2. The Python backend (without the video group: drone video is processed locally, not on a free server).
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /usr/local/bin/uv
RUN useradd -m -u 1000 user
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY templates ./templates
COPY clips ./clips
COPY --from=web /web/dist ./web/dist
RUN mkdir -p data/user_clips && chown -R user:user /app/data /app/clips

USER user
ENV PATH=/app/.venv/bin:$PATH WEB_DIST=/app/web/dist VYUH_PUBLIC=1 MPLCONFIGDIR=/tmp/matplotlib
EXPOSE 7860
CMD ["uvicorn", "tactics.api:app", "--host", "0.0.0.0", "--port", "7860"]
