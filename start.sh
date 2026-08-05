#!/bin/bash
# ============================================================
#  CyberDigest — One-click launcher (macOS & Linux)
#  Double-click start.command (macOS) or run:  bash start.sh
# ============================================================

set -e

# Always run from the folder that contains this script (double-click safe)
cd "$(cd "$(dirname "$0")" && pwd)"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${CYAN}  ╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}  ║       CyberDigest Agent              ║${NC}"
echo -e "${CYAN}  ║   One-click threat intelligence      ║${NC}"
echo -e "${CYAN}  ╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Find Python 3.10+ ──────────────────────────────────
PYTHON=""
python_supported() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        &>/dev/null
}

for cmd in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python; do
    if command -v "$cmd" &>/dev/null; then
        if python_supported "$cmd"; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${YELLOW}→${NC}  Python 3.10+ not found. Attempting automatic installation..."

    if [ "$(uname)" = "Darwin" ]; then
        if command -v brew &>/dev/null; then
            brew install python3
        else
            echo -e "${RED}❌  Install Python 3 from https://www.python.org/downloads/${NC}"
            echo "  (or install Homebrew, then re-run this script)"
            exit 1
        fi
    elif [ "$(uname -s)" = "Linux" ]; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3 python3-pip
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm python python-pip
        else
            echo -e "${RED}❌  Please install Python 3 manually.${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌  Unsupported OS. Install Python 3 manually.${NC}"
        exit 1
    fi

    for cmd in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python; do
        if command -v "$cmd" &>/dev/null; then
            if python_supported "$cmd"; then
                PYTHON="$cmd"
                break
            fi
        fi
    done

    if [ -z "$PYTHON" ]; then
        echo -e "${RED}❌  Python 3.10+ is required. Install it, then try again.${NC}"
        exit 1
    fi
fi

echo -e "  ${GREEN}✔${NC}  Python: $($PYTHON --version 2>&1)"

# ── 2. Virtual environment ────────────────────────────────
if [ -f "venv/bin/python" ] && ! python_supported "venv/bin/python"; then
    echo -e "  ${YELLOW}→${NC}  Rebuilding an incompatible virtual environment…"
    "$PYTHON" -m venv --clear venv
fi
if [ ! -f "venv/bin/python" ]; then
    echo -e "  ${YELLOW}→${NC}  Creating virtual environment (first run)…"
    "$PYTHON" -m venv venv
    echo -e "  ${GREEN}✔${NC}  Virtual environment ready"
fi

# shellcheck disable=SC1091
source venv/bin/activate

python -m pip install --quiet --upgrade pip 2>/dev/null || true

# ── 3. Dependencies ───────────────────────────────────────
echo -e "  ${YELLOW}→${NC}  Verifying pinned packages…"
if ! python -m pip install --quiet --editable .; then
    echo -e "  ${RED}❌${NC}  Package install failed. Check the internet connection and retry."
    exit 1
fi
python -m pip check
echo -e "  ${GREEN}✔${NC}  Packages ready"

# ── 4. Launch ─────────────────────────────────────────────
echo ""
echo -e "  ${CYAN}Starting CyberDigest…${NC}"
echo -e "  • Desktop: tray icon + browser report"
echo -e "  • After setup you can close this window if OS scheduling worked"
echo ""

python news_agent.py

echo ""
echo -e "  ${GREEN}✔  CyberDigest finished this session.${NC}"
echo -e "  Reports:  $(pwd)/reports/"
echo -e "  Status:   $(pwd)/status.txt"
echo -e "  Health:   python news_agent.py --healthcheck"
echo ""
