FROM public.ecr.aws/docker/library/ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates python3 jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
