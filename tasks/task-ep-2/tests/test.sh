#!/bin/bash
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d /tests ]; then
  TESTS_DIR=/tests
fi
mkdir -p /logs/verifier 2>/dev/null
python3 -m pytest -rA "$TESTS_DIR/test_outputs.py"
status=$?
reward=0
[ "$status" -eq 0 ] && reward=1
echo "reward: $reward"
if [ -d /logs/verifier ]; then
  echo "$reward" > /logs/verifier/reward.txt
fi
exit 0
