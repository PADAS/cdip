#!/usr/bin/env bash
# Usage: keycloak/tests/wait-ready.sh <url> [timeout-seconds]
# Polls until <url> returns HTTP 200. Keycloak 11 under amd64 emulation can take 3 minutes.
set -euo pipefail
url=${1:?usage: wait-ready.sh <url> [timeout-seconds]}
timeout=${2:-300}
start=$(date +%s)
until curl -sf -o /dev/null "$url"; do
  if (( $(date +%s) - start > timeout )); then
    echo "timed out after ${timeout}s waiting for $url" >&2
    exit 1
  fi
  sleep 3
done
echo "ready: $url"
