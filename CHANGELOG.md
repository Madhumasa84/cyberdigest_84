# Changelog

All notable changes to CyberDigest are documented here.

## Unreleased

### Fixed
- Restored Docker and installed-wheel execution after the `src/` layout migration.
- Scheduler jobs now run one cycle and exit instead of starting a tray or fallback loop.
- Split persistent-process and digest-run locks so scheduled work can run while the tray is open.
- Commit `last_run` and seen-article state only after reports are generated successfully.
- Keep failed or entirely unconfigured feed runs eligible for a prompt retry.
- Preserve explicitly empty feed categories in both full and minimal YAML parsing.
- Select the newest report globally rather than preferring a fixed category.
- Close network and logging resources deterministically and validate configuration ranges.

### Changed
- Require Python 3.10 or newer, matching the pinned runtime dependencies.
- Use OS user-data paths for installed packages and support `CYBERDIGEST_CONFIG_DIR`.
- Enforce Ruff formatting, 80% coverage, package validation, dependency auditing,
  and container builds in the release/CI gates.

## [4.3.0] — 2026-07-12

### Added
- NVD rate-limit budget (`nvd_max_lookups`, `nvd_timeout_seconds`, sleep knobs)
- CLI `--once` for single-run exit (no background loop)
- Multi-OS CI matrix (Ubuntu, Windows, macOS × Python 3.10/3.12)
- `pip-audit` security job in CI
- Release workflow on `v*` tags (sdist/wheel + GitHub Release)
- `SECURITY.md`, expanded tests (coverage gate **80%**)
- One-click launchers: `cd` to script dir; macOS `start.command`; Linux `.desktop` template

### Fixed
- Google security feed URL (real RSS/Atom)
- Explicit empty feed categories in `feeds.yaml` no longer fall back to defaults
- Bumped Pillow `10.2.0` → `12.2.0` (pip-audit CVEs)

### Security
- CI `pip-audit` job; `SECURITY.md` policy; `scripts/security_check.sh`

## [4.2.0] — 2026-07-12

### Added
- Package split (`cyberdigest/`), integration tests, Makefile, `verify_all.sh`
- GitHub Actions CI, coverage gate 70%
- systemd unit example

## [4.1.0] — 2026-07

### Added
- Modular architecture, tray GUI, multi-page reports, secrets via env/`config.local.json`

## [4.0.0] — 2026-06

### Added
- Production single-file agent, OS scheduling, HTML digests
