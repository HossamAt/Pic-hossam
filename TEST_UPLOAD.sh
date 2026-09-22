#!/usr/bin/env bash
set -euo pipefail
URL="${1:?Usage: ./TEST_UPLOAD.sh https://your-service.onrender.com image.jpg}"
FILE="${2:?Usage: ./TEST_UPLOAD.sh https://your-service.onrender.com image.jpg}"
curl -f -X POST "$URL/upload" -F "file=@$FILE"
echo
