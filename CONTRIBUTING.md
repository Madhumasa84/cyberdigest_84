# Contributing to CyberDigest

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
make install-dev
```

## Before you push

```bash
make verify
# or
bash scripts/verify_all.sh
```

This runs:

1. `compileall`
2. `ruff` lint
3. `pytest` with coverage ≥ 70%
4. CLI smoke (`--version`, `--help`)

## Project layout

| Path | Role |
|------|------|
| `cyberdigest/` | Application package |
| `news_agent.py` | Stable CLI entry for scripts/cron |
| `feeds.yaml` | Feed catalog (prefer editing this over Python) |
| `tests/` | Unit + integration tests (mocked network) |
| `deploy/` | systemd unit example |

## Design rules

1. **Single scheduler owner** — never run OS cron *and* the in-process loop together.
2. **Secrets stay out of git** — use `config.local.json` or env vars.
3. **Only `http`/`https` links** in reports.
4. **Enrich CVEs before HTML render**, not inside template loops.
5. **Keep `news_agent.py` thin** so existing launchers keep working.

## Tests

- Prefer isolated `tmp_path` fixtures (`tests/conftest.py`).
- Mock network I/O; do not depend on live RSS in unit tests.
- Optional live check: `python news_agent.py --force --cli-only`.

## Pull requests

- Small, focused diffs
- `make verify` green
- Update README when behavior or CLI flags change
- **DCO:** sign every commit (`git commit -s` / `--signoff`) so the
  `Signed-off-by: Your Name <email>` trailer is present. The DCO check
  fails without it.
