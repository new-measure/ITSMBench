#!/usr/bin/env bash
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d /tests ]; then
  TESTS_DIR=/tests
fi
mkdir -p /logs/verifier

ASSERTIONS_PATH="$TESTS_DIR/assertions.json" \
INITIAL_STATE_PATH="$TESTS_DIR/initial_state.json" \
VERIFIER_OUT=/logs/verifier \
  node "$TESTS_DIR/grade.js"
