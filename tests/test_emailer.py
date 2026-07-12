from cyberdigest.config import get_config, reload_config
from cyberdigest.emailer import send_email


def test_send_email_disabled_is_noop(isolated_app, monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            calls.append("init")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def sendmail(self, *a):
            calls.append("send")

    monkeypatch.setattr("cyberdigest.emailer.smtplib.SMTP", FakeSMTP)
    send_email("<html>hi</html>", "Jan 1", 3, 1)
    assert calls == []  # disabled


def test_send_email_enabled(isolated_app, monkeypatch):
    import cyberdigest.config as config_mod

    cfg = config_mod.get_config()
    cfg["email"] = {
        "enabled": True,
        "smtp_host": "smtp.test",
        "smtp_port": 587,
        "username": "u",
        "password": "p",
        "from_addr": "from@test",
        "to_addrs": ["to@test"],
    }

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self):
            calls.append("starttls")

        def login(self, u, p):
            calls.append(("login", u, p))

        def sendmail(self, frm, to, msg):
            calls.append(("sendmail", frm, to))

    monkeypatch.setattr("cyberdigest.emailer.smtplib.SMTP", FakeSMTP)
    send_email("<html>digest</html>", "Jan 1", 5, 2)
    assert any(c[0] == "sendmail" for c in calls if isinstance(c, tuple))
