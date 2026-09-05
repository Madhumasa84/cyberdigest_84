"""Configuration loading, validation, and secrets from environment."""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from typing import Any

from cyberdigest.logging_setup import log
from cyberdigest.paths import CONFIG_EXAMPLE_FILE, CONFIG_FILE, CONFIG_LOCAL_FILE

DEFAULT_CONFIG: dict[str, Any] = {
    "interval_days": 3,
    "max_archived_reports": 30,
    # When True, the cap applies across ALL report categories combined.
    # When False (legacy), each category keeps up to max_archived_reports files.
    "archive_global": True,
    "max_articles_per_feed": 8,
    "max_articles_per_network_feed": 5,
    "log_level": "INFO",
    "critical_keywords": [
        "cve-",
        "zero-day",
        "0-day",
        "actively exploited",
        "rce",
        "ransomware",
        "breach",
        "critical vulnerability",
        "outage",
        "bgp hijack",
        "backbone failure",
        "ddos",
    ],
    "high_keywords": [
        "vulnerability",
        "flaw",
        "patch",
        "exploit",
        "malware",
        "deprecat",
        "end-of-life",
        "eol",
        "misconfiguration",
        "sd-wan",
        "firmware update",
        "security advisory",
    ],
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "",
        "password": "",
        "from_addr": "",
        "to_addrs": [],
    },
    "nvd_api_key": "",
    # NVD rate-limit budget (keeps digests snappy without an API key)
    "nvd_enabled": True,
    "nvd_max_lookups": 15,  # live HTTP lookups per run (cache free)
    "nvd_timeout_seconds": 25,  # wall-clock seconds for all live lookups
    "nvd_sleep_no_key": 0.6,  # polite delay without API key
    "nvd_sleep_with_key": 0.2,  # delay with API key
}

_CONFIG_REQUIRED_TYPES: dict[str, type] = {
    "interval_days": int,
    "max_archived_reports": int,
    "archive_global": bool,
    "max_articles_per_feed": int,
    "max_articles_per_network_feed": int,
    "log_level": str,
    "critical_keywords": list,
    "high_keywords": list,
    "nvd_enabled": bool,
    "nvd_max_lookups": int,
    "nvd_api_key": str,
}

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _apply_env_secrets(cfg: dict) -> dict:
    """Overlay secrets from environment (never commit these)."""
    email = cfg.setdefault("email", {})
    if not isinstance(email, dict):
        email = {}
        cfg["email"] = email
    if os.environ.get("CYBERDIGEST_SMTP_PASSWORD"):
        email["password"] = os.environ["CYBERDIGEST_SMTP_PASSWORD"]
    if os.environ.get("CYBERDIGEST_SMTP_USERNAME"):
        email["username"] = os.environ["CYBERDIGEST_SMTP_USERNAME"]
    if os.environ.get("CYBERDIGEST_SMTP_HOST"):
        email["smtp_host"] = os.environ["CYBERDIGEST_SMTP_HOST"]
    if os.environ.get("CYBERDIGEST_SMTP_PORT"):
        try:
            email["smtp_port"] = int(os.environ["CYBERDIGEST_SMTP_PORT"])
        except ValueError:
            pass
    if os.environ.get("CYBERDIGEST_EMAIL_FROM"):
        email["from_addr"] = os.environ["CYBERDIGEST_EMAIL_FROM"]
    if os.environ.get("CYBERDIGEST_EMAIL_TO"):
        raw = os.environ["CYBERDIGEST_EMAIL_TO"]
        email["to_addrs"] = [a.strip() for a in raw.split(",") if a.strip()]
    email_enabled = os.environ.get("CYBERDIGEST_EMAIL_ENABLED", "").strip().lower()
    if email_enabled in _TRUE_VALUES | _FALSE_VALUES:
        email["enabled"] = email_enabled in _TRUE_VALUES
    if os.environ.get("NVD_API_KEY"):
        cfg["nvd_api_key"] = os.environ["NVD_API_KEY"]
    elif os.environ.get("CYBERDIGEST_NVD_API_KEY"):
        cfg["nvd_api_key"] = os.environ["CYBERDIGEST_NVD_API_KEY"]
    if os.environ.get("CYBERDIGEST_INTERVAL_DAYS"):
        try:
            cfg["interval_days"] = int(os.environ["CYBERDIGEST_INTERVAL_DAYS"])
        except ValueError:
            pass
    return cfg


def _validate_required_types(cfg: dict) -> list[str]:
    errors: list[str] = []
    for key, expected in _CONFIG_REQUIRED_TYPES.items():
        val = cfg.get(key)
        valid = isinstance(val, expected)
        if expected is int and isinstance(val, bool):
            valid = False
        if not valid:
            errors.append(f"config: '{key}' must be {expected.__name__}, got {type(val).__name__}")
    return errors


def _validate_numeric_ranges(cfg: dict) -> list[str]:
    errors: list[str] = []
    for key in (
        "interval_days",
        "max_archived_reports",
        "max_articles_per_feed",
        "max_articles_per_network_feed",
    ):
        value = cfg.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value < 1:
            errors.append(f"config: '{key}' must be >= 1")
    nvd_lookups = cfg.get("nvd_max_lookups")
    if isinstance(nvd_lookups, int) and not isinstance(nvd_lookups, bool) and nvd_lookups < 0:
        errors.append("config: 'nvd_max_lookups' must be >= 0")
    for key in ("nvd_timeout_seconds", "nvd_sleep_no_key", "nvd_sleep_with_key"):
        value = cfg.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            errors.append(f"config: '{key}' must be a number")
        elif value < 0:
            errors.append(f"config: '{key}' must be >= 0")
    return errors


def _validate_text_settings(cfg: dict) -> list[str]:
    errors: list[str] = []
    if str(cfg.get("log_level", "")).upper() not in {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }:
        errors.append("config: 'log_level' must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    for key in ("critical_keywords", "high_keywords"):
        values = cfg.get(key)
        if isinstance(values, list) and not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            errors.append(f"config: '{key}' must contain only non-empty strings")
    return errors


def _validate_email(email: Any) -> list[str]:
    if not isinstance(email, dict):
        return ["config: 'email' must be an object"]
    if not isinstance(email.get("enabled"), bool):
        return ["config: email.enabled must be a boolean"]
    if not email["enabled"]:
        return []

    errors = [
        f"config: email.{field} is required when email.enabled=true"
        for field in ("smtp_host", "username", "password", "from_addr")
        if not email.get(field)
    ]
    recipients = email.get("to_addrs")
    if not recipients:
        errors.append("config: email.to_addrs must have at least one address")
    elif not isinstance(recipients, list) or not all(
        isinstance(address, str) and address.strip() for address in recipients
    ):
        errors.append("config: email.to_addrs must be a list of non-empty strings")
    port = email.get("smtp_port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        errors.append("config: email.smtp_port must be an integer from 1 to 65535")
    return errors


def validate_config(cfg: dict) -> list[str]:
    return (
        _validate_required_types(cfg)
        + _validate_numeric_ranges(cfg)
        + _validate_text_settings(cfg)
        + _validate_email(cfg.get("email", {}))
    )


def _write_default_config() -> None:
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = deepcopy(DEFAULT_CONFIG)
        CONFIG_FILE.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
        log.info("Created default config.json")
    except Exception as exc:
        log.warning("Could not write config.json: %s", exc)
    if not CONFIG_EXAMPLE_FILE.exists():
        try:
            example = deepcopy(DEFAULT_CONFIG)
            example["email"]["password"] = ""
            example["nvd_api_key"] = ""
            example["_comment"] = (
                "Copy to config.local.json for secrets, or set env vars: "
                "CYBERDIGEST_SMTP_PASSWORD, NVD_API_KEY"
            )
            CONFIG_EXAMPLE_FILE.write_text(json.dumps(example, indent=4) + "\n", encoding="utf-8")
        except Exception as exc:
            log.debug("Could not write config.example.json: %s", exc)


def load_config(*, exit_on_error: bool = True) -> dict:
    if not CONFIG_FILE.exists():
        _write_default_config()
        cfg = deepcopy(DEFAULT_CONFIG)
    else:
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config.json root must be an object")
            cfg = _deep_merge(DEFAULT_CONFIG, raw)
        except (json.JSONDecodeError, ValueError) as exc:
            log.error("config.json is invalid: %s", exc)
            if exit_on_error:
                print(f"[CONFIG ERROR] config.json is invalid: {exc}")
                sys.exit(1)
            raise

    # Optional local overrides (gitignored) — ideal for passwords/API keys
    if CONFIG_LOCAL_FILE.exists():
        try:
            local = json.loads(CONFIG_LOCAL_FILE.read_text(encoding="utf-8"))
            if not isinstance(local, dict):
                raise ValueError("config.local.json root must be an object")
            cfg = _deep_merge(cfg, local)
            log.info("Loaded config.local.json overrides")
        except (json.JSONDecodeError, ValueError) as exc:
            log.error("config.local.json is invalid: %s", exc)
            if exit_on_error:
                print(f"[CONFIG ERROR] config.local.json is invalid: {exc}")
                sys.exit(1)
            raise

    cfg = _apply_env_secrets(cfg)
    errors = validate_config(cfg)
    if errors:
        for e in errors:
            log.error("Config error: %s", e)
        if exit_on_error:
            print("\n".join(f"[CONFIG ERROR] {e}" for e in errors))
            sys.exit(1)
        raise ValueError("; ".join(errors))

    from cyberdigest.logging_setup import setup_logging

    setup_logging(cfg.get("log_level", "INFO"))
    return cfg


# Module-level config loaded on first import of agent/cli
CONFIG: dict[str, Any] = {}


def get_config() -> dict:
    global CONFIG
    if not CONFIG:
        CONFIG = load_config()
    return CONFIG


def reload_config() -> dict:
    global CONFIG
    CONFIG = load_config()
    return CONFIG
