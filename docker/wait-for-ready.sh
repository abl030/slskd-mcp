#!/usr/bin/env bash
# Wait for slskd to be healthy, then extract/create an API key.
set -euo pipefail

MAX_WAIT=120
CONTAINER="slskd-test"

echo "Waiting for slskd to be healthy..."
for i in $(seq 1 "$MAX_WAIT"); do
    status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")
    if [ "$status" = "healthy" ]; then
        echo "slskd is healthy after ${i}s"

        # slskd with SLSKD_NO_AUTH=true doesn't need an API key,
        # but we still need one for our client. Check if there's a default.
        # With no-auth mode, any non-empty key works.
        API_KEY="test-api-key"
        echo "API Key: $API_KEY"
        echo ""
        echo "Set environment:"
        echo "  export SLSKD_URL=http://localhost:15030"
        echo "  export SLSKD_API_KEY=$API_KEY"
        exit 0
    fi
    sleep 1
done

echo "slskd failed to become healthy within ${MAX_WAIT}s"
exit 1
