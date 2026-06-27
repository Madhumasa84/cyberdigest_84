#!/bin/bash
# ============================================================
#  CyberDigest — Universal Launcher (macOS & Linux)
#  Just run:  bash start.sh
# ============================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo -e "${CYAN}  ╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}  ║       🛡️  CyberDigest Agent           ║${NC}"
echo -e "${CYAN}  ║   Automated Threat Intelligence      ║${NC}"
echo -e "${CYAN}  ╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Find Python 3 ──────────────────────────────────────
PYTHON=""
for cmd in python3 python3.12 python3.11 python3.10 python3.9 python3.8 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
        if [ "$VER" = "3" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${YELLOW}→${NC}  Python 3 not found. Attempting automatic installation..."
    
    if [ "$(uname)" == "Darwin" ]; then
        if command -v brew &>/dev/null; then
            echo -e "  Using Homebrew to install Python..."
            brew install python3
        else
            echo -e "${RED}❌  Homebrew not found.${NC}"
            echo "  Please install Python manually from https://www.python.org/downloads/"
            exit 1
        fi
    elif [ "$(uname -s)" == "Linux" ]; then
        if command -v apt-get &>/dev/null; then
            echo -e "  Using apt-get to install Python (may ask for sudo password)..."
            sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
        elif command -v dnf &>/dev/null; then
            echo -e "  Using dnf to install Python (may ask for sudo password)..."
            sudo dnf install -y python3 python3-pip
        elif command -v pacman &>/dev/null; then
            echo -e "  Using pacman to install Python (may ask for sudo password)..."
            sudo pacman -S --noconfirm python3 python-pip
        else
            echo -e "${RED}❌  Unsupported package manager. Please install Python 3 manually.${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌  Unsupported OS for auto-install. Please install Python 3 manually.${NC}"
        exit 1
    fi

    # Re-detect Python after installation
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            VER=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
            if [ "$VER" = "3" ]; then
                PYTHON="$cmd"
                break
            fi
        fi
    done
    
    if [ -z "$PYTHON" ]; then
        echo -e "${RED}❌  Installation seemed to succeed, but Python 3 is still not found.${NC}"
        echo "  You may need to restart your terminal."
        exit 1
    fi
fi

echo -e "  ${GREEN}✔${NC}  Python found: $($PYTHON --version)"

# ── 2. Create virtual environment ─────────────────────────
if [ ! -f "venv/bin/python" ]; then
    echo -e "  ${YELLOW}→${NC}  Creating virtual environment..."
    "$PYTHON" -m venv venv
    echo -e "  ${GREEN}✔${NC}  Virtual environment created"
fi

source venv/bin/activate

# ── 3. Upgrade pip silently ────────────────────────────────
python -m pip install --quiet --upgrade pip 2>/dev/null || true

# ── 4. Install / verify dependencies ──────────────────────
echo -e "  ${YELLOW}→${NC}  Checking dependencies..."
if ! python -c "import feedparser, schedule, plyer" &>/dev/null 2>&1; then
    echo -e "  ${YELLOW}→${NC}  Installing packages (first run — takes ~30 seconds)..."
    pip install --quiet -r requirements.txt
    echo -e "  ${GREEN}✔${NC}  All packages installed"
else
    echo -e "  ${GREEN}✔${NC}  All packages ready"
fi

# ── 5. Launch ─────────────────────────────────────────────
echo ""
echo -e "  ${CYAN}Fetching your cybersecurity digest…${NC}"
echo -e "  The report will open in your browser automatically."
echo -e "  The agent will then run silently every 3 days."
echo -e "  You can safely close this window after setup completes."
echo ""

python news_agent.py

echo ""
echo -e "  ${GREEN}✔  Done! CyberDigest is running in the background.${NC}"
echo ""
