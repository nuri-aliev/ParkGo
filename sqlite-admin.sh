#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$project_dir/.venv/bin/sqlite_web" \
  --host 127.0.0.1 \
  --password \
  "$project_dir/parking.db"
