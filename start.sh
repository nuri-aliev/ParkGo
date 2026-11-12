#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Optional local server configuration; never commit this file.
if [[ -f "${PARKGO_ENV_FILE:-.env}" ]]; then
    set -a
    source "${PARKGO_ENV_FILE:-.env}"
    set +a
fi

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import flask; from qrcode.image.svg import SvgPathFillImage' 2>/dev/null; then
    .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python app.py "$@"
