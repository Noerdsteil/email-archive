#!/bin/sh
# Import everything new in bronze/: parse -> build -> restart. Prints the parser metrics. Safe to rerun; only new mail is embedded.
set -e
cd "$(dirname "$0")"
docker compose run --rm app python parse.py
docker compose run --rm app python gold.py build
docker compose restart
echo "done -> http://localhost:8000"
