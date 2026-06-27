#  CyberDigest

> **A self-healing, reboot-proof cybersecurity news agent for everyone.**  
> Clone it. Run one file. Get a beautiful daily digest — forever.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

---

##  What it does

CyberDigest automatically pulls cybersecurity news from **9 trusted sources** every 3 days and generates a stunning, interactive HTML report that opens right in your browser.

- 🔴 **Critical** / 🟠 **High** / 🔵 **Normal** severity scoring  
-  **Live search** - filter by keyword, CVE ID, or source  
-  **CVSS scores** pulled live from the NVD database  
-  **30-day rolling window** - old news auto-deleted, always fresh  
-  **Runs forever in the background** - survives reboots automatically  
-  **Archive page** - browse all past digests  

---

##  Quick Start (3 steps)

### Step 1 - Clone the repo

```bash
git clone https://github.com/Madhumasa84/cyberdigest_84.git
cd cyberdigest
```

### Step 2 - Run the launcher

| OS | Command |
|---|---|
| **Windows** | Double-click `start.bat` |
| **macOS / Linux** | Run `bash start.sh` in terminal |

> That's it. The launcher installs Python packages, runs the agent, and registers it to run automatically every 3 days - even after a reboot.

### Step 3 - Done 

Your browser opens with the digest. Close the terminal window. The agent runs silently in the background forever.

---

##  Docker (For Servers / Advanced Users)

Want to run it headlessly on a 24/7 server without the desktop UI? Just use Docker:

```bash
git clone https://github.com/YOUR_USERNAME/cyberdigest.git
cd cyberdigest
docker-compose up -d
```
Docker will build the environment and run the agent entirely in the background. It automatically detects it's running headlessly and skips browser popups, safely writing your reports to the `reports/` folder.

---

##  Requirements

- **Python 3.8+** - [Download here](https://www.python.org/downloads/) *(check "Add to PATH" on Windows)*
- Internet connection
- ~50 MB disk space

No other setup needed - everything else is installed automatically.

---

##  Project Structure

```
cyberdigest/
├── news_agent.py       ← The entire agent (single file)
├── start.sh            ← Launcher for macOS / Linux
├── start.bat           ← Launcher for Windows
├── requirements.txt    ← Python dependencies
├── config.json         ← Auto-generated settings (editable)
├── state.db            ← Article history database (auto-created)
├── status.txt          ← Last run summary (human-readable)
├── heartbeat.txt       ← Proof the agent is alive
├── agent_log.txt       ← Detailed technical log
└── reports/
    ├── index.html      ← Archive of all past digests
    └── cybersec_report_YYYYMMDD_HHMM.html
```

---

##  Configuration

Edit `config.json` (auto-created on first run) to customise behaviour:

```json
{
    "interval_days": 3,
    "max_archived_reports": 30,
    "max_articles_per_feed": 8,
    "critical_keywords": ["cve-", "zero-day", "ransomware", "breach", "rce"],
    "high_keywords": ["vulnerability", "flaw", "patch"],
    "email": {
        "enabled": false,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "your_email@gmail.com",
        "password": "your_app_password",
        "from_addr": "your_email@gmail.com",
        "to_addrs": ["recipient@example.com"]
    },
    "nvd_api_key": ""
}
```

> **Email setup:** Set `"enabled": true` and provide your SMTP details to have the digest automatically emailed to you every run.
> **NVD API Key:** Getting a free key from the [National Vulnerability Database](https://nvd.nist.gov/developers/request-an-api-key) prevents rate-limiting and makes CVE lookups much faster.

After editing, run the launcher once to re-register the new schedule.

---

##  CLI Commands

```bash
# Force a run immediately (ignores the 3-day interval check)
python3 news_agent.py --force

# Full health report - scheduler, DB, feeds, disk, internet, lock files
python3 news_agent.py --healthcheck

# Remove background scheduling (keeps all reports)
python3 news_agent.py --uninstall
```

---

## 📡 News Sources

| Source | Focus |
|---|---|
| The Hacker News | General cybersecurity |
| Krebs on Security | Investigations & breaches |
| Schneier on Security | Analysis & policy |
| CISA Advisories | US government alerts |
| Sophos Threat Research | Malware & threats |
| Microsoft Security Blog | Windows & cloud |
| Cloudflare Security | Infrastructure & DDoS |
| WeLiveSecurity (ESET) | Malware research |
| Graham Cluley | News & commentary |

---

##  How Scheduling Works

| OS | Method |
|---|---|
| Windows | Task Scheduler (`schtasks`) |
| macOS | LaunchAgent (`launchctl`) |
| Linux | Cron (`crontab`) |

The agent **verifies** the task was registered after creating it. If registration fails, it falls back to an in-process loop and shows a notice in the report.

---

##  FAQ

**Q: Do I need to keep the terminal open?**  
No. The OS scheduler takes over after the first run. Close it freely.

**Q: My internet was down when it ran. What happens?**  
The agent detects the outage, waits 30 minutes, and retries - no empty reports.

**Q: I was away for 2 weeks. Did I miss digests?**  
No. Missed-run catch-up kicks in the moment your computer turns on.

**Q: How do I completely uninstall?**  
Run `python3 news_agent.py --uninstall`, then delete the folder.

**Q: Can I add my own RSS feeds?**  
Yes , edit the `FEEDS` list near the top of `news_agent.py`.

---

##  License

MIT - free for personal and commercial use.
