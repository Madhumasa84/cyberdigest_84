#!/usr/bin/env bash
# Full local verification for CyberDigest (no Docker required).
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}✔${NC}  $1"; }
fail() { echo -e "${RED}✘${NC}  $1"; exit 1; }
info() { echo -e "${YELLOW}→${NC}  $1"; }

echo ""
echo "══════════════════════════════════════════"
echo "  CyberDigest — full verification"
echo "══════════════════════════════════════════"
echo ""

if [[ ! -x venv/bin/python ]]; then
  info "Creating venv..."
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -e .[dev]

info "1/6 Compile"
python -m compileall -q src/cyberdigest news_agent.py
pass "compileall"

info "2/6 Lint (ruff)"
if ruff check src/cyberdigest tests news_agent.py; then
  pass "ruff"
else
  fail "ruff found issues"
fi

info "3/7 Tests + coverage ≥80%"
pytest -q --cov=cyberdigest --cov-report=term-missing --cov-fail-under=80
pass "pytest + coverage"

info "4/6 CLI smoke"
python news_agent.py --version
python -m cyberdigest --version
python news_agent.py --help >/dev/null
pass "CLI --version / --help"

info "5/6 Healthcheck (live network — non-fatal feed failures)"
set +e
python news_agent.py --healthcheck
hc=$?
set -e
if [[ $hc -eq 0 ]]; then
  pass "healthcheck HEALTHY"
else
  echo -e "${YELLOW}⚠${NC}  healthcheck reported issues (exit $hc) — often feed/network flakiness"
fi

info "6/7 Package import surface"
python - <<'PY'
from cyberdigest import __version__
from cyberdigest.feeds import load_feeds
assert __version__
feeds = load_feeds()
assert sum(len(v) for v in feeds.values()) >= 10
print(f"  version={__version__} feeds={ {k: len(v) for k,v in feeds.items()} }")
PY
pass "imports + feed catalog"

info "7/7 Security (pip-audit)"
pip install -q pip-audit
if pip-audit -r requirements.txt; then
  pass "pip-audit clean"
else
  echo -e "${YELLOW}⚠${NC}  pip-audit reported findings — review before release"
fi

echo ""
echo "══════════════════════════════════════════"
echo -e "  ${GREEN}All automated checks finished${NC}"
echo "══════════════════════════════════════════"
echo ""
echo "One-click for users:"
echo "  Windows:  double-click start.bat"
echo "  macOS:    double-click start.command"
echo "  Linux:    bash start.sh"
echo ""
echo "Optional live digest:"
echo "  python news_agent.py --force --once --cli-only"
echo ""
