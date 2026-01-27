"""Email client for sending responses via SMTP.

All configuration is passed as parameters to avoid import-time side effects.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(
    to_address: str,
    subject: str,
    body: str,
    email_user: str,
    email_pass: str,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> bool:
    """Send an email via SMTP.

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        email_user: SMTP username/sender address.
        email_pass: SMTP password/app password.
        smtp_server: SMTP server hostname.
        smtp_port: SMTP server port.

    Returns:
        True if email was sent successfully, False otherwise.
    """
    if not email_user or not email_pass:
        print("Error: email_user or email_pass not provided")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = email_user
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(email_user, to_address, msg.as_string())

        print(f"Email sent to {to_address}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
