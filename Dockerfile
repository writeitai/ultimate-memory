FROM ghcr.io/astral-sh/uv:0.11.31@sha256:ecd4de2f060c64bea0ff8ecb182ddf46ba3fcccdc8a60cfdbaf20d1a047d7437 AS uv

FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

COPY --from=uv /uv /uvx /bin/

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE alembic.ini ./

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /var/lib/ultimate-memory/forget-manifests \
    && chown -R app:app /var/lib/ultimate-memory \
    && uv sync --locked --no-dev --extra server --no-install-project

COPY src ./src

RUN uv sync --locked --no-dev --extra server

USER app

ENTRYPOINT ["python", "-m", "ultimate_memory.profiles.selfhost"]
CMD ["api"]
