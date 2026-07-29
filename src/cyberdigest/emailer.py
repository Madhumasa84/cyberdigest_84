"""Optional SMTP digest delivery."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from cyberdigest.config import get_config
from cyberdigest.logging_setup import log


def send_email(
    html_content: str, report_date: str, n_articles: int, n_crit: int
) -> None:
    em = get_config().get("email", {})
    if not em.get("enabled"):
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"CyberDigest — {report_date} ({n_articles} articles, {n_crit} critical)"
        )
        msg["From"] = em["from_addr"]
        msg["To"] = ", ".join(em["to_addrs"])
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP(em["smtp_host"], em["smtp_port"], timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(em["username"], em["password"])
            smtp.sendmail(em["from_addr"], em["to_addrs"], msg.as_string())

        log.info("Email sent to: %s", em["to_addrs"])
    except Exception as exc:
        log.error("Email delivery failed: %s", exc)
