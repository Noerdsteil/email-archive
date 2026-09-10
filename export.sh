#!/bin/sh
# Bundle the folder for another machine: code, gold.db, silver/, bronze/ (needed for attachments).
# Leaves out .git, .venv, models/ (the model is inside the Docker image) and older exports.
# Unzip on the target, `docker compose up -d`, done.
set -e
cd "$(dirname "$0")"
out="email-archive-$(date +%Y%m%d).zip"
rm -f "$out"
zip -qr "$out" . -x '.git/*' '.venv/*' 'models/*' '*/__pycache__/*' '__pycache__/*' '*.DS_Store' 'email-archive-*.zip'
echo "$out  $(du -h "$out" | cut -f1)"
