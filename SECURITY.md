# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 4.3.x   | ✅ |
| 4.2.x   | ✅ (security fixes) |
| < 4.2   | ❌ |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Email or DM the maintainer via the GitHub profile linked in the repository, with:

1. Description of the issue  
2. Steps to reproduce  
3. Impact assessment (if known)  
4. Any suggested fix  

You should receive an acknowledgement within a few days.

## Security design notes

- **Secrets:** Never commit passwords or API keys. Use `config.local.json` (gitignored) or environment variables (`NVD_API_KEY`, `CYBERDIGEST_SMTP_PASSWORD`, …).
- **Links:** Report HTML only allows `http://` and `https://` article URLs.
- **HTML:** User-facing strings from feeds are escaped before embedding.
- **Dependencies:** CI runs `pip-audit` on every push/PR.
- **Docker:** Prefer env vars for secrets; do not bake credentials into images.

## Dependency updates

```bash
pip install pip-audit
pip-audit -r requirements.txt
```

Or: `bash scripts/security_check.sh`
