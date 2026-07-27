#!/bin/bash
if ! command -v python3 >/dev/null 2>&1; then
  apt-get update && apt-get install -y --no-install-recommends python3
fi
exec python3 "$(dirname "$0")/solution.py"
