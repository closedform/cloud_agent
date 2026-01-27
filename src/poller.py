"""Email poller - the ears of the agent.

Watches Gmail for incoming commands, parses intent, and drops task files
for the orchestrator to process.
"""

import email
import email.utils
import imaplib
import time
import uuid
from email.header import decode_header
from email.message import Message

from src.config import Config, get_config
from src.models import Task
from src.task_io import write_task_atomic


def connect_imap(config: Config) -> imaplib.IMAP4_SSL:
    """Connect to IMAP server and login."""
    mail = imaplib.IMAP4_SSL(config.imap_server)
    mail.login(config.email_user, config.email_pass)
    return mail


def clean_filename(filename: str) -> str:
    """Sanitize filename for filesystem safety."""
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"])


def get_email_body(msg: Message) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode()
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode()
    return body


def save_attachments(msg: Message, task_id: str, config: Config) -> list[str]:
    """Save email attachments and return list of filenames."""
    attachments = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue

        filename = part.get_filename()
        if filename:
            safe_name = f"{task_id}_{clean_filename(filename)}"
            filepath = config.input_dir / safe_name
            payload = part.get_payload(decode=True)
            if payload:
                with open(filepath, "wb") as f:
                    f.write(payload)
                attachments.append(safe_name)
                print(f"  Saved attachment: {safe_name}")
    return attachments


def extract_reply_to(subject: str) -> str:
    """Extract reply-to email from subject if present.

    Handles patterns like 'Research: me@example.com'
    """
    if ":" in subject:
        after_colon = subject.split(":", 1)[1].strip()
        first_word = after_colon.split()[0] if after_colon.split() else ""
        if "@" in first_word and "." in first_word:
            return first_word
    return ""


def generate_task_id() -> str:
    """Generate a unique task ID using UUID4."""
    return uuid.uuid4().hex


def create_task(
    task_id: str,
    subject: str,
    body: str,
    sender: str,
    attachments: list[str],
    config: Config,
) -> str:
    """Create a task file in the inputs directory."""
    # Try to extract reply_to from subject (e.g., "Research: me@example.com")
    reply_to = extract_reply_to(subject)
    if not reply_to:
        reply_to = sender

    task = Task(
        id=task_id,
        subject=subject,
        body=body,
        sender=sender,
        reply_to=reply_to,
        attachments=attachments,
    )

    task_file = config.input_dir / f"task_{task.id}.json"
    write_task_atomic(task.to_dict(), task_file)

    return task.id


def process_emails(config: Config) -> None:
    """Check for new emails and create tasks."""
    if not config.allowed_senders:
        print("Warning: No ALLOWED_SENDERS configured.")
        return

    mail = None
    try:
        mail = connect_imap(config)
        mail.select("inbox")

        for sender in config.allowed_senders:
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
                        subject_header = decode_header(msg["Subject"])[0][0]
                        if isinstance(subject_header, bytes):
                            subject = subject_header.decode()
                        else:
                            subject = subject_header

                        print(f"Received: {subject}")

                        # Get body
                        body = get_email_body(msg)

                        # Generate task ID (used for both attachments and task file)
                        task_id = generate_task_id()

                        # Save attachments if any
                        attachments = save_attachments(msg, task_id, config)

                        # Create task file (orchestrator will classify intent)
                        create_task(task_id, subject, body, sender, attachments, config)
                        print(f"  -> Created task {task_id}")

    except Exception as e:
        print(f"Email Error: {e}")
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass


def main() -> None:
    """Main entry point for the poller."""
    config = get_config()

    print(f"Poller started (interval: {config.poll_interval}s)...")
    config.input_dir.mkdir(exist_ok=True)

    while True:
        process_emails(config)
        time.sleep(config.poll_interval)


if __name__ == "__main__":
    main()
