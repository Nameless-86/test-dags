#!/usr/bin/env bash
set -e

QDRANT_URL="http://localhost:6333"
SEARCH_API_URL="http://localhost:8000/search"

collections=$(curl -s "${QDRANT_URL}/collections" | jq -r '.result.collections[].name')

if [ -z "$collections" ]; then
  echo "ERROR: No collections found in Qdrant."
  exit 1
fi

for collection in $collections; do
  point_count=$(curl -s "${QDRANT_URL}/collections/${collection}/points/count" -H "Content-Type: application/json" -d '{}' | jq '.result.count')
  if [ "$point_count" -lt 1 ]; then
    echo "ERROR: Collection '$collection' is empty."
    exit 1
  fi

  http_status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$SEARCH_API_URL" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"CPU usage high\", \"top_k\":1, \"collection\":\"$collection\"}")

  if [ "$http_status" -ne 200 ]; then
    echo "ERROR: Search endpoint failed for collection '$collection'."
    exit 1
  fi
done

echo "All collections passed validation."
