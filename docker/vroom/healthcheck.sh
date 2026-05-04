#!/usr/bin/env sh
set -eu
status="$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/health)"
if [ "$status" != "200" ]; then
  echo "VROOM healthcheck failed with HTTP $status" >&2
  exit 1
fi
echo "VROOM healthcheck OK"
