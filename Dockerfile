FROM python:3.13-slim-bookworm

WORKDIR /app
COPY . .
RUN pip install . && pip cache purge && rm -rf /app/*

ENTRYPOINT ["crpy"]
