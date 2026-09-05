---
name: testing-cyberdigest-html
description: Test locally generated CyberDigest HTML reports and their browser controls.
---

# CyberDigest report UI testing

Use the repository blueprint's editable installation (`venv/bin/pip install -e
".[dev]"`). There is no web server: reports are self-contained HTML with embedded
CSS/JS, opened via `file://` in Chrome. External font loading is optional.

## Deterministic renderer coverage

When synthetic articles are authorized, call
`cyberdigest.reports.generate_html(articles, report_date, health_data,
sched_warn, feeds_list)` and write its returned string to a temporary HTML file.
Each article needs `title`, `summary`, `source`, `severity`, `timestamp`,
`published`, and `link`. Use an unmistakable synthetic source label and
example.com links. This bypasses live feeds, scoring, enrichment, and persistence;
do not describe it as coverage of those systems.

Choose timestamps that put Critical last under initial newest ordering. Then use
the native "Sort: Severity" dropdown to demonstrate an actual ordering change.
The visual card grid reads left-to-right, top-to-bottom. Include Normal and an
unknown severity only when testing fallback behavior, and verify both badges and
summary/tab counts. Test severity tabs together with search (including a
zero-result conjunction), then clear filters to verify recovery.

No application source edits or backend services are needed. Generate in a fresh
Python process after source changes because report assets load at import time.

## Devin Secrets Needed

None for local report generation or browser UI checks. Live NVD/email workflows
are separate and may require the documented application credentials.
