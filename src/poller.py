"""Email poller - the ears of the agent.

Watches Gmail for incoming commands, parses intent, and drops task files
for the orchestrator to process.
"""

import os
import time
import json
import email
import email.utils
import imaplib
from email.header import decode_header
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Configuration
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
allowed_senders_env = os.getenv("ALLOWED_SENDERS", "")
ALLOWED_SENDERS = [s.strip() for s in allowed_senders_env.split(",") if s.strip()]
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

IMAP_SERVER = "imap.gmail.com"
INPUT_DIR = Path("inputs")


def connect_imap():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_USER, EMAIL_PASS)
    return mail


def clean_filename(filename: str) -> str:
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"])


def get_email_body(msg) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                body = part.get_payload(decode=True).decode()
                break
    else:
        body = msg.get_payload(decode=True).decode()
    return body


def save_attachments(msg, task_id: str) -> list:
    """Save email attachments and return list of filenames."""
    attachments = []
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        filename = part.get_filename()
        if filename:
            safe_name = f"{task_id}_{clean_filename(filename)}"
            filepath = INPUT_DIR / safe_name
            with open(filepath, "wb") as f:
                f.write(part.get_payload(decode=True))
            attachments.append(safe_name)
            print(f"  Saved attachment: {safe_name}")
    return attachments


def extract_reply_to(subject: str) -> str:
    """Extract reply-to email from subject if present (e.g., 'Research: me@example.com')."""
    # Check for common patterns where email follows a colon
    if ":" in subject:
        after_colon = subject.split(":", 1)[1].strip()
        # Check if first word looks like an email
        first_word = after_colon.split()[0] if after_colon.split() else ""
        if "@" in first_word and "." in first_word:
            return first_word
    return ""


def create_task(subject: str, body: str, sender: str, attachments: list) -> str:
    """Create a task file in the inputs directory."""
    task_id = str(int(time.time() * 1000))

    # Try to extract reply_to from subject (e.g., "Research: me@example.com")
    reply_to = extract_reply_to(subject)
    if not reply_to:
        reply_to = sender

    task = {
        "id": task_id,
        "subject": subject,
        "body": body,
        "sender": sender,
        "reply_to": reply_to,
        "attachments": attachments,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }

    task_file = INPUT_DIR / f"task_{task_id}.json"
    with open(task_file, "w") as f:
        json.dump(task, f, indent=2)

    return task_id


def process_emails():
    """Check for new emails and create tasks."""
    if not ALLOWED_SENDERS:
        print("Warning: No ALLOWED_SENDERS configured.")
        return

    try:
        mail = connect_imap()
        mail.select("inbox")

        for sender in ALLOWED_SENDERS:
            status, messages = mail.search(None, f'(UNSEEN FROM "{sender}")')
            email_ids = messages[0].split()

            if not email_ids:
                continue

            print(f"Found {len(email_ids)} new emails from {sender}...")

            for e_id in email_ids:
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = decode_header(msg["Subject"])[0][0]
                        if isinstance(subject, bytes):
                            subject = subject.decode()

                        print(f"Received: {subject}")

                        # Get body
                        body = get_email_body(msg)

                        # Generate task ID for attachments
                        task_id = str(int(time.time() * 1000))

                        # Save attachments if any
                        attachments = save_attachments(msg, task_id)

                        # Create task file (orchestrator will classify intent)
                        create_task(subject, body, sender, attachments)
                        print(f"  -> Created task")

    except Exception as e:
        print(f"Email Error: {e}")
    finally:
        try:
            mail.close()
            mail.logout()
        except:
            pass


def main():
    print(f"Poller started (interval: {POLL_INTERVAL}s)...")
    INPUT_DIR.mkdir(exist_ok=True)

    while True:
        process_emails()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
