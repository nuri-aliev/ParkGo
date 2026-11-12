#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import flask' 2>/dev/null; then
    .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python app.py "$@"
