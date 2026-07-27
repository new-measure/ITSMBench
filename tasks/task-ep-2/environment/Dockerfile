FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl jq ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --no-cache-dir requests==2.32.3 pytest==8.3.4

WORKDIR /app
