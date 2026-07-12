"""Additional config validation / write paths."""

from __future__ import annotations

import json

from cyberdigest import config as config_mod


def test_validate_nvd_fields():
    cfg = dict(config_mod.DEFAULT_CONFIG)
    cfg["nvd_max_lookups"] = -1
    errs = config_mod.validate_config(cfg)
    assert any("nvd_max_lookups" in e for e in errs)


def test_validate_email_enabled():
    cfg = dict(config_mod.DEFAULT_CONFIG)
    cfg["email"] = {
        "enabled": True,
        "smtp_host": "",
        "username": "",
        "password": "",
        "from_addr": "",
        "to_addrs": [],
    }
    errs = config_mod.validate_config(cfg)
    assert len(errs) >= 3


def test_write_default_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config_mod, "CONFIG_LOCAL_FILE", tmp_path / "config.local.json")
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_FILE", tmp_path / "config.example.json")
    config_mod.CONFIG = {}
    cfg = config_mod.load_config(exit_on_error=False)
    assert (tmp_path / "config.json").exists()
    assert cfg["interval_days"] == 3
    assert "nvd_max_lookups" in cfg


def test_invalid_json_raises(monkeypatch, tmp_path):
    bad = tmp_path / "config.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", bad)
    monkeypatch.setattr(config_mod, "CONFIG_LOCAL_FILE", tmp_path / "config.local.json")
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_FILE", tmp_path / "config.example.json")
    config_mod.CONFIG = {}
    try:
        config_mod.load_config(exit_on_error=False)
        assert False, "expected error"
    except Exception:
        pass
