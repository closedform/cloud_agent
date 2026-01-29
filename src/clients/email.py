"""Email client for sending responses via SMTP.

All configuration is passed as parameters to avoid import-time side effects.
Supports both plain text and HTML emails.
"""

import html as html_module
import smtplib
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _escape_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS.

    Args:
        text: Text that may contain HTML special characters.

    Returns:
        Escaped text safe for insertion into HTML.
    """
    return html_module.escape(text)


def send_email(
    to_address: str,
    subject: str,
    body: str,
    email_user: str,
    email_pass: str,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
    html_body: str | None = None,
) -> bool:
    """Send an email via SMTP.

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        body: Email body text (plain text fallback).
        email_user: SMTP username/sender address.
        email_pass: SMTP password/app password.
        smtp_server: SMTP server hostname.
        smtp_port: SMTP server port.
        html_body: Optional HTML body (if provided, sends multipart email).

    Returns:
        True if email was sent successfully, False otherwise.
    """
    if not email_user or not email_pass:
        print("Error: email_user or email_pass not provided")
        return False

    if not to_address or not to_address.strip():
        print("Error: to_address is empty")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = email_user
        msg["To"] = to_address
        msg["Subject"] = subject

        # Always attach plain text version
        msg.attach(MIMEText(body, "plain"))

        # Attach HTML version if provided
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.login(email_user, email_pass)
            server.sendmail(email_user, to_address, msg.as_string())

        print(f"Email sent to {to_address}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        # Authentication failure - likely bad credentials
        print(f"SMTP authentication failed: {e}")
        return False

    except smtplib.SMTPRecipientsRefused as e:
        # Recipient address rejected
        print(f"Recipient refused ({to_address}): {e}")
        return False

    except smtplib.SMTPException as e:
        # Other SMTP errors
        print(f"SMTP error sending to {to_address}: {e}")
        return False

    except (socket.timeout, socket.error) as e:
        # Network-level errors (transient, may succeed on retry)
        print(f"Network error sending email: {e}")
        return False

    except ssl.SSLError as e:
        # TLS/SSL errors
        print(f"SSL error sending email: {e}")
        return False

    except Exception as e:
        # Catch-all for unexpected errors
        print(f"Unexpected error sending email: {type(e).__name__}: {e}")
        return False


# === HTML Email Templates ===

EMAIL_STYLE = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; }
    .header h1 { margin: 0; font-size: 24px; }
    .content { background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px; }
    .section { background: white; padding: 15px; margin: 10px 0; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .section h2 { color: #667eea; font-size: 18px; margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 8px; }
    .weather-day { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #eee; }
    .weather-day:last-child { border-bottom: none; }
    .temp { font-weight: bold; color: #667eea; }
    .condition { color: #666; }
    .event { padding: 8px 0; border-bottom: 1px solid #eee; }
    .event:last-child { border-bottom: none; }
    .event-time { color: #667eea; font-weight: bold; }
    .footer { text-align: center; color: #999; font-size: 12px; margin-top: 20px; }
    .reminder-box { background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 10px 0; }
    .success { color: #28a745; }
    .info { color: #17a2b8; }
</style>
"""


def html_weekly_schedule(
    weather_html: str,
    calendar_html: str,
    greeting: str = "Here's your schedule for the upcoming week",
) -> str:
    """Generate HTML for weekly schedule email.

    Args:
        weather_html: Pre-formatted weather HTML (from format_weather_html).
        calendar_html: Pre-formatted calendar HTML (from format_calendar_html).
        greeting: Optional greeting message (will be escaped for security).

    Returns:
        Complete HTML email body.
    """
    # Escape greeting to prevent XSS (weather_html and calendar_html are
    # pre-formatted by format_weather_html and format_calendar_html which
    # already escape their content)
    safe_greeting = _escape_html(greeting)

    return f"""<!DOCTYPE html>
<html>
<head>{EMAIL_STYLE}</head>
<body>
    <div class="header">
        <h1>📅 Weekly Schedule & Forecast</h1>
    </div>
    <div class="content">
        <p>{safe_greeting}</p>

        <div class="section">
            <h2>🌤️ Weather Forecast</h2>
            {weather_html}
        </div>

        <div class="section">
            <h2>📆 Your Calendar</h2>
            {calendar_html}
        </div>
    </div>
    <div class="footer">
        Sent by Cloud Agent • Your AI assistant
    </div>
</body>
</html>"""


def html_response(
    content: str,
    title: str = "Response",
    icon: str = "💬",
) -> str:
    """Generate HTML for a general response email.

    Args:
        content: Main content (can include HTML).
        title: Email title (will be escaped for security).
        icon: Emoji icon for header (will be escaped for security).

    Returns:
        Complete HTML email body.
    """
    # Escape title and icon to prevent XSS
    safe_title = _escape_html(title)
    safe_icon = _escape_html(icon)

    return f"""<!DOCTYPE html>
<html>
<head>{EMAIL_STYLE}</head>
<body>
    <div class="header">
        <h1>{safe_icon} {safe_title}</h1>
    </div>
    <div class="content">
        <div class="section">
            {content}
        </div>
    </div>
    <div class="footer">
        Sent by Cloud Agent • Your AI assistant
    </div>
</body>
</html>"""


def html_reminder(message: str, original_time: str) -> str:
    """Generate HTML for a reminder email.

    Args:
        message: Reminder message (will be escaped for security).
        original_time: When the reminder was originally set (will be escaped for security).

    Returns:
        Complete HTML email body.
    """
    # Escape user-provided content to prevent XSS
    safe_message = _escape_html(message)
    safe_time = _escape_html(original_time)

    return f"""<!DOCTYPE html>
<html>
<head>{EMAIL_STYLE}</head>
<body>
    <div class="header">
        <h1>⏰ Reminder</h1>
    </div>
    <div class="content">
        <div class="reminder-box">
            <strong>{safe_message}</strong>
        </div>
        <p style="color: #666; font-size: 14px;">Originally set: {safe_time}</p>
    </div>
    <div class="footer">
        Sent by Cloud Agent • Your AI assistant
    </div>
</body>
</html>"""


def format_weather_html(forecasts: list[dict]) -> str:
    """Format weather forecasts as HTML.

    Args:
        forecasts: List of forecast dictionaries.

    Returns:
        HTML string for weather section.
    """
    rows = []
    for day in forecasts[:7]:
        # Escape all external data to prevent XSS
        day_name = _escape_html(str(day.get("day", "")))
        date = _escape_html(str(day.get("date", "")))
        high = _escape_html(str(day.get("high", day.get("high_f", "?"))))
        low = _escape_html(str(day.get("low", day.get("low_f", "?"))))
        condition = _escape_html(str(day.get("condition", "")))
        precip = day.get("precipitation_chance", day.get("rain_chance", ""))

        precip_str = f" - {_escape_html(str(precip))}" if precip and str(precip).replace("%", "").isdigit() and int(str(precip).replace("%", "")) > 20 else ""

        rows.append(f"""
            <div class="weather-day">
                <span><strong>{day_name}</strong> <span style="color:#999">({date})</span></span>
                <span><span class="temp">{low}° - {high}°F</span> <span class="condition">{condition}{precip_str}</span></span>
            </div>
        """)

    return "\n".join(rows)


def format_calendar_html(events_by_calendar: dict[str, list[dict]]) -> str:
    """Format calendar events as HTML.

    Args:
        events_by_calendar: Dictionary mapping calendar names to event lists.

    Returns:
        HTML string for calendar section.
    """
    if not events_by_calendar:
        return "<p>No events scheduled.</p>"

    sections = []
    for cal_name, events in events_by_calendar.items():
        if not events:
            continue

        event_html = []
        for event in events[:10]:
            # Escape external data to prevent XSS
            start = _escape_html(str(event.get("start", "")))
            summary = _escape_html(str(event.get("summary", "Untitled")))
            event_html.append(f"""
                <div class="event">
                    <span class="event-time">{start}</span>: {summary}
                </div>
            """)

        # Escape calendar name
        safe_cal_name = _escape_html(cal_name.title())
        sections.append(f"""
            <h3 style="color: #764ba2; margin-bottom: 10px;">{safe_cal_name}</h3>
            {"".join(event_html)}
        """)

    return "\n".join(sections)


def text_to_html(text: str) -> str:
    """Convert plain text with basic markdown to HTML.

    Supports:
    - **bold** -> <strong>bold</strong>
    - *italic* -> <em>italic</em>
    - Paragraphs (double newlines)
    - Line breaks (single newlines)

    SECURITY: All input is escaped to prevent XSS attacks.
    Previously, HTML-like content was passed through unescaped, which was
    a security vulnerability allowing script injection.

    Args:
        text: Plain text content with optional markdown.

    Returns:
        HTML-formatted content with all special characters escaped.
    """
    import re

    # ALWAYS escape HTML entities to prevent XSS
    # This is the secure approach - never trust input to be "safe HTML"
    escaped = html_module.escape(text)

    # Convert markdown bold **text** to <strong>bold</strong>
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)

    # Convert markdown italic *text* to <em>italic</em> (but not ** which is bold)
    escaped = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', escaped)

    # Convert bullet points (- item or * item at start of line)
    escaped = re.sub(r'(?m)^[-*]\s+(.+)$', r'<li>\1</li>', escaped)
    # Wrap consecutive <li> items in <ul>
    escaped = re.sub(r'((?:<li>.*?</li>\n?)+)', r'<ul>\1</ul>', escaped)

    # Convert double newlines to paragraphs
    paragraphs = escaped.split("\n\n")
    html_parts = [f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip()]

    return "\n".join(html_parts)
