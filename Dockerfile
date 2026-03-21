FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS builder

WORKDIR /app
COPY . .
RUN uv build

FROM python:3.14-slim-trixie

COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

ENTRYPOINT ["crpy"]
CMD ["--help"]
