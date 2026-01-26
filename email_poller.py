import os
import time
import email
import imaplib
from email.header import decode_header
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Configuration
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
# Security: Allow list (comma-separated in .env)
allowed_senders_env = os.getenv("ALLOWED_SENDERS", "")
ALLOWED_SENDERS = [s.strip() for s in allowed_senders_env.split(",") if s.strip()]
# Polling Interval (seconds), default to 60
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

IMAP_SERVER = "imap.gmail.com"
INPUT_DIR = Path("inputs")

def connect_imap():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_USER, EMAIL_PASS)
    return mail

def clean_filename(filename):
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"])

def process_email():
    if not ALLOWED_SENDERS:
        print("Warning: No ALLOWED_SENDERS configured.")
        return

    try:
        mail = connect_imap()
        mail.select("inbox")

        # Check each allowed sender
        for sender in ALLOWED_SENDERS:
            # Search for UNSEEN emails from this specific sender
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
                        
                        subject_lower = subject.lower()
                        print(f"Received Email: {subject}")

                        # Routing Logic
                        if any(keyword in subject_lower for keyword in ["calendar", "schedule", "appointment"]):
                            print(f"  -> Routing to Calendar Agent")
                            process_calendar_email(msg, subject)
                        else:
                            print(f"  -> Subject does not match known intents. Skipping.")
                            # Future: elif "to-do" in subject_lower: process_todo_email(msg)

    except Exception as e:
        print(f"Email Error: {e}")
    finally:
        try:
            mail.close()
            mail.logout()
        except:
            pass

def process_calendar_email(msg, subject):
    # 1. Save Body as Text File
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if content_type == "text/plain" and "attachment" not in content_disposition:
                body = part.get_payload(decode=True).decode()
    else:
        body = msg.get_payload(decode=True).decode()

    if body.strip():
        # Create a text file input
        timestamp = int(time.time())
        txt_filename = f"email_{timestamp}.txt"
        with open(INPUT_DIR / txt_filename, "w") as f:
            f.write(f"Context from Email Subject: {subject}\n\n{body}")
        print(f"Saved body to {txt_filename}")

    # 2. Save Attachments
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
            
        filename = part.get_filename()
        if filename:
            filepath = INPUT_DIR / clean_filename(filename)
            with open(filepath, "wb") as f:
                f.write(part.get_payload(decode=True))
            print(f"Saved attachment to {filepath.name}")

def main():
    print(f"Email Poller Started (Interval: {POLL_INTERVAL}s)...")
    INPUT_DIR.mkdir(exist_ok=True)
    
    while True:
        process_email()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
