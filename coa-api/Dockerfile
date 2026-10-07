FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev
COPY . .
# State (trace.db, checkpoints.db, uploads/) lives on the compose volume.
ENV STATE_DIR=/state
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "fastapi", "run", "main.py", "--port", "8000"]
