#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x venv/bin/python ]]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt pip-audit

echo "→ pip-audit"
pip-audit -r requirements.txt
echo "✔  No known vulnerabilities in pinned requirements (or review findings above)"
