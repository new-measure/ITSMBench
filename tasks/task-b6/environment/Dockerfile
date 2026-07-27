FROM public.ecr.aws/docker/library/node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates jq \
    && npm install -g @earendil-works/pi-coding-agent@0.80.2 \
    && pi --version \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/* /root/.npm /tmp/*

WORKDIR /app
