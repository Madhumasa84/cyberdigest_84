#!/bin/bash
# macOS double-click launcher (same as start.sh)
cd "$(cd "$(dirname "$0")" && pwd)"
exec bash "./start.sh"
