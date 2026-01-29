"""Email poller - the ears of the agent.

Watches Gmail for incoming commands, parses intent, and drops task files
for the orchestrator to process.
"""

import email
import email.utils
import imaplib
import socket
import time
import uuid
from email.header import decode_header
from email.message import Message

from src.config import Config, get_config
from src.models import Task
from src.task_io import write_task_atomic

# IMAP connection timeout in seconds
IMAP_TIMEOUT = 30


def connect_imap(config: Config) -> imaplib.IMAP4_SSL:
    """Connect to IMAP server and login.

    Uses socket timeout to prevent hanging on network issues.
    The timeout is set per-connection rather than globally to avoid
    affecting other concurrent operations.
    """
    # Create connection with timeout parameter (Python 3.9+)
    # This avoids modifying the global socket timeout
    mail = imaplib.IMAP4_SSL(config.imap_server, timeout=IMAP_TIMEOUT)
    try:
        mail.login(config.email_user, config.email_pass)
        return mail
    except Exception:
        # Clean up the connection on login failure
        try:
            mail.logout()
        except Exception:
            pass
        raise


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
                    # Try common encodings, fallback to replace errors
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body = payload.decode(charset)
                    except (UnicodeDecodeError, LookupError):
                        body = payload.decode("utf-8", errors="replace")
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                body = payload.decode(charset)
            except (UnicodeDecodeError, LookupError):
                body = payload.decode("utf-8", errors="replace")
    return body


def decode_filename(filename: str | None) -> str | None:
    """Decode RFC 2047 encoded filename if necessary."""
    if filename is None:
        return None

    # Handle RFC 2047 encoded filenames (e.g., =?utf-8?b?...?=)
    decoded_parts = decode_header(filename)
    result_parts = []
    for data, charset in decoded_parts:
        if isinstance(data, bytes):
            try:
                result_parts.append(data.decode(charset or "utf-8"))
            except (UnicodeDecodeError, LookupError):
                result_parts.append(data.decode("utf-8", errors="replace"))
        else:
            result_parts.append(data)
    return "".join(result_parts) if result_parts else filename


def save_attachments(msg: Message, task_id: str, config: Config) -> list[str]:
    """Save email attachments and return list of filenames."""
    attachments = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue

        filename = decode_filename(part.get_filename())
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


def decode_subject(msg: Message) -> str:
    """Safely decode email subject header.

    Handles:
    - Missing Subject header
    - RFC 2047 encoded subjects
    - Invalid charset encoding
    """
    raw_subject = msg["Subject"]
    if raw_subject is None:
        return "(No Subject)"

    try:
        decoded_parts = decode_header(raw_subject)
    except Exception:
        # decode_header can raise on malformed headers
        return str(raw_subject) if raw_subject else "(No Subject)"

    result_parts = []
    for data, charset in decoded_parts:
        if isinstance(data, bytes):
            try:
                result_parts.append(data.decode(charset or "utf-8"))
            except (UnicodeDecodeError, LookupError):
                result_parts.append(data.decode("utf-8", errors="replace"))
        else:
            result_parts.append(data if data else "")

    return "".join(result_parts) or "(No Subject)"


def process_emails(config: Config) -> None:
    """Check for new emails and create tasks."""
    if not config.allowed_senders:
        print("Warning: No ALLOWED_SENDERS configured.")
        return

    mail = None
    mailbox_selected = False
    try:
        mail = connect_imap(config)
        select_result = mail.select("inbox")

        # Handle select result - real IMAP returns tuple (status, data)
        if isinstance(select_result, tuple) and len(select_result) >= 1:
            if select_result[0] != "OK":
                print(f"Failed to select inbox: {select_result[0]}")
                return
        mailbox_selected = True

        for sender in config.allowed_senders:
            try:
                # Security: Sanitize sender to prevent IMAP command injection
                # Remove characters that could break out of the quoted string
                safe_sender = sender.replace('"', '').replace('\\', '').replace('\r', '').replace('\n', '')
                if safe_sender != sender:
                    print(f"Warning: Sanitized sender '{sender}' to '{safe_sender}'")
                search_result = mail.search(None, f'(UNSEEN FROM "{safe_sender}")')

                # Extract status and messages from search result
                if isinstance(search_result, tuple) and len(search_result) >= 2:
                    status, messages = search_result[0], search_result[1]
                    if status != "OK":
                        print(f"Search failed for {sender}: {status}")
                        continue
                    email_ids = messages[0].split() if messages[0] else []
                else:
                    # Fallback for unexpected format
                    continue

                if not email_ids:
                    continue

                print(f"Found {len(email_ids)} new emails from {sender}...")

                for e_id in email_ids:
                    try:
                        fetch_result = mail.fetch(e_id, "(RFC822)")

                        # Extract status and data from fetch result
                        if isinstance(fetch_result, tuple) and len(fetch_result) >= 2:
                            status, msg_data = fetch_result[0], fetch_result[1]
                            if status != "OK":
                                print(f"  Failed to fetch email {e_id}: {status}")
                                continue
                        else:
                            print(f"  Unexpected fetch result for {e_id}")
                            continue

                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                subject = decode_subject(msg)

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

                    except (imaplib.IMAP4.error, socket.error) as e:
                        print(f"  IMAP error fetching email {e_id}: {e}")
                        # Connection may be broken, stop processing this cycle
                        raise

            except (imaplib.IMAP4.error, socket.error) as e:
                print(f"IMAP error searching for {sender}: {e}")
                # Connection may be broken, stop processing
                raise

    except (imaplib.IMAP4.error, socket.error, socket.timeout) as e:
        print(f"IMAP connection error: {e}")
    except Exception as e:
        print(f"Email Error: {e}")
    finally:
        if mail:
            try:
                # Only close mailbox if it was successfully selected
                if mailbox_selected:
                    mail.close()
                mail.logout()
            except Exception:
                pass


def main() -> None:
    """Main entry point for the poller."""
    import signal
    import sys

    config = get_config()

    # Shutdown flag
    shutdown_requested = False

    def signal_handler(signum: int, frame) -> None:
        nonlocal shutdown_requested
        print("\nPoller shutdown requested...")
        shutdown_requested = True

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"Poller started (interval: {config.poll_interval}s)...")
    config.input_dir.mkdir(exist_ok=True)

    try:
        while not shutdown_requested:
            try:
                process_emails(config)
            except Exception as e:
                # Log unexpected errors but keep running
                print(f"Unexpected error in process_emails: {e}")
                import traceback
                traceback.print_exc()

            # Sleep in small increments to check shutdown flag
            for _ in range(config.poll_interval):
                if shutdown_requested:
                    break
                time.sleep(1)
    finally:
        print("Poller stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
