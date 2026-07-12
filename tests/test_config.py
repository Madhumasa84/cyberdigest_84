import json
import os
from pathlib import Path

from cyberdigest import config as config_mod


def test_env_secret_overlay(monkeypatch, tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config_mod.DEFAULT_CONFIG), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_path)
    monkeypatch.setattr(config_mod, "CONFIG_LOCAL_FILE", tmp_path / "config.local.json")
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_FILE", tmp_path / "config.example.json")
    monkeypatch.setenv("CYBERDIGEST_SMTP_PASSWORD", "secret-pass")
    monkeypatch.setenv("NVD_API_KEY", "nvd-key-123")
    monkeypatch.delenv("CYBERDIGEST_EMAIL_ENABLED", raising=False)

    config_mod.CONFIG = {}
    cfg = config_mod.load_config(exit_on_error=False)
    assert cfg["email"]["password"] == "secret-pass"
    assert cfg["nvd_api_key"] == "nvd-key-123"


def test_local_config_merge(monkeypatch, tmp_path):
    base = dict(config_mod.DEFAULT_CONFIG)
    base["interval_days"] = 3
    (tmp_path / "config.json").write_text(json.dumps(base), encoding="utf-8")
    (tmp_path / "config.local.json").write_text(
        json.dumps({"interval_days": 7, "nvd_api_key": "local-key"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config_mod, "CONFIG_LOCAL_FILE", tmp_path / "config.local.json")
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_FILE", tmp_path / "config.example.json")
    for k in list(os.environ):
        if k.startswith("CYBERDIGEST_") or k == "NVD_API_KEY":
            monkeypatch.delenv(k, raising=False)

    config_mod.CONFIG = {}
    cfg = config_mod.load_config(exit_on_error=False)
    assert cfg["interval_days"] == 7
    assert cfg["nvd_api_key"] == "local-key"
