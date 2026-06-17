# email_sender.py
"""
Minimal email sender.
If SMTP not configured, prints email to console.
"""

import os
import smtplib
from email.mime.text import MIMEText


def send_email(subject, body, sender, recipient, smtp_config=None):
    if smtp_config:
        host = smtp_config.get("host")
        port = smtp_config.get("port")
        user = smtp_config.get("user")
        pwd  = smtp_config.get("password")
    else:
        host = os.getenv("QKD_SMTP_HOST")
        port = os.getenv("QKD_SMTP_PORT")
        user = os.getenv("QKD_SMTP_USER")
        pwd  = os.getenv("QKD_SMTP_PASS")

    if not host:
        print("\n===== EMAIL OUTPUT (SIMULATED) =====")
        print("To:", recipient)
        print("From:", sender)
        print("Subject:", subject)
        print(body)
        print("====================================\n")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    with smtplib.SMTP(host, int(port)) as server:
        server.starttls()
        if user and pwd:
            server.login(user, pwd)
        server.sendmail(sender, [recipient], msg.as_string())
