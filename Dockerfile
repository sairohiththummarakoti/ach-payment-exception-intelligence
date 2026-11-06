FROM ghcr.io/astral-sh/uv:0.10.12 AS uv
FROM python:3.12.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev && useradd --create-home analyst
COPY data ./data
RUN chown analyst:analyst /app
USER analyst
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=4)"
CMD ["uvicorn", "ach_intelligence.api:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
