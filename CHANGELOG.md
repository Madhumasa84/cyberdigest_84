# Changelog

All notable changes to CyberDigest are documented here.

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
