================================================================
        CYBERSECURITY NEWS AGENT
================================================================

WHAT IS THIS?
-------------
This program automatically collects the latest cybersecurity news
from 9 trusted security websites and shows you a beautiful daily
digest in your web browser.

You do NOT need to type any commands, edit any files, or know
anything about programming. Just double-click a file and you're done.


HOW TO START IT (3 STEPS)
-------------------------

STEP 1 - Install Python (only the first time, one-time setup)
   * Windows: Go to https://www.python.org/downloads/ and download
     Python 3. Make sure to check the box that says
     "Add Python to PATH" before clicking Install.
   * Mac: Install Python 3 from https://www.python.org/downloads/
   * Linux: Python 3 is usually already installed. If not, open a
     terminal and run:  sudo apt install python3 python3-venv

STEP 2 - Double-click the launcher for your computer
   * Windows:  Double-click  start.bat
   * Mac/Linux: Open a terminal in this folder and run:
                bash start.sh
        (If double-click doesn't work on Mac, right-click start.sh
         -> Open With -> Terminal.)

STEP 3 - Sit back! The agent runs automatically forever.
   The first run will set everything up and show your digest.
   After that, it silently registers itself with your computer's
   operating system (Task Scheduler, LaunchAgents, or Cron) to 
   wake up every 3 days, even after a reboot. You can safely close 
   the terminal window. 


WHAT YOU'LL SEE
---------------
- A notification: "Your cybersecurity digest is ready! Check your browser."
- Your web browser opens with a styled page containing all
  the latest articles.
- Similar stories from different sources are merged automatically.
- Severe vulnerabilities are color-coded, and CVE IDs fetch real-time
  CVSS scores from the public NVD database.


WHERE ARE THE FILES SAVED?
--------------------------
- Reports (HTML files, plus an index.html archive of past reports):
      reports/cybersec_report_YYYYMMDD.html
- The database tracking your history and feed health:
      state.db
- A human-readable status check:
      status.txt (open this to check when it last ran and if feeds are healthy)
- Agent Heartbeat:
      heartbeat.txt (the exact timestamp of the last background wake-up)
- Settings file:
      config.json (generated automatically with safe defaults)
- A detailed technical log:
      agent_log.txt


ADVANCED COMMANDS
-----------------

If you ever need to troubleshoot or stop the agent entirely, you can run
these commands from your terminal/command prompt in this folder:

* Check Health:
  python3 news_agent.py --healthcheck
  (Prints a plain-English status report showing if the scheduler is active, 
   disk space, database health, and if feeds are reachable.)

* Uninstall OS Scheduler:
  python3 news_agent.py --uninstall
  (Cleanly removes the background scheduled task from your operating system.)


COMMON QUESTIONS
----------------

Q: Do I need to keep the black window open?
A: No! The agent registers itself with your operating system to run automatically
   in the background every 3 days. You can safely close the window after the first run.
   (Note: If the OS scheduler fails to register for some reason, the report will show 
   a warning telling you to leave the window open.)

Q: I turned my computer off for a week. Did I miss my digests?
A: No! The agent features missed-run catch-up. As soon as you turn your computer
   back on, it realizes it missed a scheduled run and will fetch your news immediately.

Q: My internet was down when it tried to run. What happens?
A: The agent has total-outage detection. If your internet drops, it will quietly 
   pause and try again every 30 minutes until the connection is restored, 
   without spamming you with empty reports.

Q: How do I change how often it runs?
A: Open the auto-generated config.json file and change "interval_days" to your
   preferred number. You will need to run the agent manually once for the new
   schedule to register with your operating system.

Q: How do I uninstall completely?
A: First, run `python3 news_agent.py --uninstall` to cleanly remove the background
   tasks. Then, simply delete this folder.


REQUIREMENTS
------------
- Windows 10/11, macOS 10.13+, or any modern Linux.
- An internet connection.
- About 100 MB of free disk space.

Enjoy your daily cybersecurity briefing!
================================================================
