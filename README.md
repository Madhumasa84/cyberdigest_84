# CyberDigest

> **A self-healing, reboot-proof cybersecurity news agent.**  
> Clone it. Run one command. Get multi-page HTML digests — forever.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/badge/version-4.3-informational)
![CI](https://img.shields.io/badge/CI-ubuntu%20%7C%20windows%20%7C%20macos-success)
![Coverage](https://img.shields.io/badge/coverage-%E2%89%A580%25-brightgreen)

---

## What it does

CyberDigest pulls news from **24+ sources** across four categories and builds interactive HTML digests:

| Report | Focus |
|--------|--------|
| **Cybersecurity** | Threat intel, breaches, research blogs, CISA KEV |
| **Networking** | Enterprise networking, cloud, architecture |
| **Cisco PSIRT** | Official Cisco security advisories |
| **Fortinet PSIRT** | Official Fortinet security advisories |

**Highlights**

- Severity scoring (Critical / High / Normal) with CVE-aware heuristics  
- Live CVSS badges from NVD (cached in SQLite)  
- Cross-source fuzzy deduplication  
- Archive page with rolling retention  
- System tray GUI (desktop) or headless Docker (servers)  
- OS-native scheduling **or** single in-process fallback (never both)  
- Optional email delivery via SMTP  

---

## Quick start (one click)

### 1. Clone (once)

```bash
git clone https://github.com/Madhumasa84/cyberdigest_84.git
cd cyberdigest_84
```

### 2. Start — pick your OS

| OS | One-click action |
|----|------------------|
| **Windows** | Double-click **`start.bat`** |
| **macOS** | Double-click **`start.command`** *(right-click → Open the first time if Gatekeeper blocks it)* |
| **Linux** | Double-click **`start.sh`** in the file manager, or run `bash start.sh` |

The launcher:

1. Switches to the project folder (safe for double-click)  
2. Finds or installs Python 3.10+
3. Creates `venv` and installs packages on first run  
4. Starts CyberDigest (tray on desktop, report in browser)  
5. Registers OS scheduling when possible  

### 3. Done

- Browser opens the digest  
- Tray icon (desktop) for “Fetch now” / “Open latest”  
- Close the terminal after setup if scheduling registered  

**No config required** for the default experience. Optional: `config.local.json` or env vars for NVD/email secrets.

---

## Docker (servers)

```bash
git clone https://github.com/Madhumasa84/cyberdigest_84.git
cd cyberdigest_84
docker compose up -d
```

- Runs headlessly (`CYBERDIGEST_HEADLESS=1`)
- Persists state in a named volume (`cyberdigest-data`)
- Writes HTML reports to `./reports` on the host
- Uses an in-process schedule (no host cron required)

---

## Project structure

```
cyberdigest_84/
├── news_agent.py           # Backward-compatible entrypoint
├── src/cyberdigest/        # Installable application package
│   ├── agent.py            # Fetch → score → enrich → report pipeline
│   ├── feeds.py            # Feed catalog + fetch/parse
│   ├── scoring.py          # Severity + clustering
│   ├── enrich.py           # CVE/NVD enrichment (pre-render, budgeted)
│   ├── reports.py          # HTML generators
│   ├── scheduler.py        # cron / schtasks / launchd
│   ├── tray.py             # System tray GUI
│   ├── config.py           # Config + env secrets
│   ├── db.py               # SQLite
│   ├── cli.py              # CLI entry
│   └── assets/             # CSS / JS for reports
├── feeds.yaml              # Editable feed list (no code changes)
├── config.json             # Non-secret settings (safe defaults)
├── config.example.json     # Documented template
├── config.local.json       # Optional secrets (gitignored)
├── start.bat               # Windows one-click
├── start.command           # macOS one-click
├── start.sh                # Linux / macOS launcher
├── requirements.txt
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── CHANGELOG.md
├── SECURITY.md
├── deploy/                 # systemd unit + .desktop shortcut
├── scripts/                # verify_all.sh, security_check.sh
├── .github/workflows/      # CI (3 OS) + release
└── tests/
```

Runtime data (gitignored): `state.db`, `reports/`, `agent_log.txt`, `status.txt`,
`heartbeat.txt`, `agent.lock`, and `run.lock`.

Source checkouts keep data in the repository folder. Installed wheels use the OS
user-data directory unless `CYBERDIGEST_DATA_DIR` is set.

---

## Configuration

### `config.json`

```json
{
    "interval_days": 3,
    "max_archived_reports": 30,
    "archive_global": true,
    "max_articles_per_feed": 8,
    "max_articles_per_network_feed": 5,
    "log_level": "INFO",
    "email": { "enabled": false },
    "nvd_api_key": "",
    "nvd_enabled": true,
    "nvd_max_lookups": 15,
    "nvd_timeout_seconds": 25
}
```

| Key | Meaning |
|-----|---------|
| `archive_global` | `true` = max N reports **total**; `false` = N **per category** |
| `interval_days` | Days between digests |
| `nvd_max_lookups` | Max live NVD HTTP calls per run (cache free) |
| `nvd_timeout_seconds` | Wall-clock budget for live NVD lookups |

### Secrets (do not commit)

Prefer **environment variables** or **`config.local.json`** (gitignored):

| Variable | Purpose |
|----------|---------|
| `NVD_API_KEY` / `CYBERDIGEST_NVD_API_KEY` | NVD rate limits |
| `CYBERDIGEST_SMTP_PASSWORD` | SMTP password / app password |
| `CYBERDIGEST_SMTP_USERNAME` | SMTP user |
| `CYBERDIGEST_EMAIL_FROM` / `CYBERDIGEST_EMAIL_TO` | Addresses |
| `CYBERDIGEST_EMAIL_ENABLED` | `true` or `false` email override |
| `CYBERDIGEST_HEADLESS` | Force headless mode |
| `CYBERDIGEST_DATA_DIR` | Relocate DB/logs/reports |
| `CYBERDIGEST_CONFIG_DIR` | Relocate config and `feeds.yaml` |

Example `config.local.json`:

```json
{
    "nvd_api_key": "your-nvd-key",
    "email": {
        "enabled": true,
        "username": "you@gmail.com",
        "password": "app-password",
        "from_addr": "you@gmail.com",
        "to_addrs": ["you@gmail.com"]
    }
}
```

### Feeds

Edit `feeds.yaml` to add or remove sources. No Python edits required.

---

## CLI

```bash
# Normal run (tray on desktop, CLI when headless)
python3 news_agent.py

# Or as a module
python3 -m cyberdigest

# Force a run now (still exits after one cycle)
python3 news_agent.py --force

# One digest then exit — no background loop (great for servers/cron)
python3 news_agent.py --once --cli-only

# Force + one-shot
python3 news_agent.py --force --once --cli-only

# Health report
python3 news_agent.py --healthcheck

# Health report that requires OS scheduler (desktop installs)
python3 news_agent.py --healthcheck --require-scheduler

# CLI only (no tray; may keep a fallback loop unless --once)
python3 news_agent.py --cli-only

# Remove OS schedule
python3 news_agent.py --uninstall

# Version
python3 news_agent.py --version
```

---

## Scheduling model

| Context | Behavior |
|---------|----------|
| Desktop + OS schedule OK | OS cron/schtasks/launchd only |
| Desktop + schedule failed | In-process `schedule` loop (keep process alive) |
| Docker / headless | In-process loop only (no host crontab mutation) |
| Explicit `--cli-only` | In-process loop only (no competing OS registration) |
| `--once` / `--force` | One cycle, protected by a dedicated run lock, then exit |
| Tray open + OS schedule | Tray does **not** double-run; OS fires separate jobs |

OS schedulers perform one lightweight due check each day. The configured
`interval_days` is enforced by CyberDigest itself, avoiding cron month-boundary
errors and allowing a failed cycle to retry the next day. In-process fallback
modes check hourly, while still generating reports only when the interval is due.

---

## Development & quality bar

```bash
python3 -m venv venv
source venv/bin/activate
make install-dev

# Full local gate (lint + coverage ≥80% + CLI smoke + pip-audit)
make verify
# or
bash scripts/verify_all.sh

# Tests / security only
make test
make test-cov
make security
```

| Check | Command | Gate |
|-------|---------|------|
| Lint | `ruff check …` | clean |
| Unit + integration | `pytest` | all green |
| Coverage | `pytest --cov=cyberdigest` | **≥ 80%** |
| Dependency audit | `pip-audit -r requirements.txt` | clean |
| CLI smoke | `--version` / `--help` | exit 0 |
| CI | Ubuntu + Windows + macOS | on push/PR |
| Release | tag `v*` | build + GitHub Release |

Production Linux: `deploy/cyberdigest.service`. Desktop shortcut template:
`deploy/cyberdigest.desktop`. Both templates assume the checkout is installed at
`/opt/cyberdigest`.

### NVD budget (keeps digests fast)

| Config key | Default | Meaning |
|------------|---------|---------|
| `nvd_enabled` | `true` | Master switch |
| `nvd_max_lookups` | `15` | Max live NVD HTTP calls per run |
| `nvd_timeout_seconds` | `25` | Wall-clock budget for live lookups |
| `nvd_api_key` / `NVD_API_KEY` | empty | Higher rate limits when set |

Cache hits do not count toward the budget.

---

## News sources (defaults)

See `feeds.yaml` for the full list. Includes The Hacker News, Krebs, Schneier, CISA KEV, Cisco Talos, Unit 42, Microsoft Security, Dark Reading, Network World, Packet Pushers, Cisco/Fortinet PSIRT, and more.

---

## FAQ

**Is it really one click?**  
After clone/unzip: yes — double-click `start.bat` / `start.command` / `start.sh`. First run installs packages (~30s). macOS may ask you to “Open” once (Gatekeeper). Linux may need “Allow executing as program” on `start.sh`.

**Do I need to keep the terminal open?**  
Only if OS scheduling failed (fallback loop), or you used `--cli-only` without `--once`. Otherwise close freely after setup.

**Internet was down during a run?**  
Persistent modes wait and retry. One-shot jobs exit non-zero so cron, systemd, or
another orchestrator can retry; failed runs do not advance the successful-run timestamp.

**How do I uninstall?**  
`python3 news_agent.py --uninstall`, then delete the folder.

**Where do I put API keys?**  
`config.local.json` or environment variables — never commit them. See `SECURITY.md`.

**Why are some CVSS badges missing?**  
NVD lookups are budgeted per run (`nvd_max_lookups` / `nvd_timeout_seconds`) so digests stay fast. Set `NVD_API_KEY` for more lookups and higher rate limits. Cached scores are reused next run.

---

## License

MIT — free for personal and commercial use. See `CHANGELOG.md` for version history.
