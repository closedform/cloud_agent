import os
import time
import email
import email.utils
import imaplib
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

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
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
INPUT_DIR = Path("inputs")

# Gemini client for research
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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
                        if subject_lower.startswith("research:"):
                            print(f"  -> Routing to Research Agent")
                            query = subject[9:].strip()  # Remove "research:" prefix
                            sender_email = email.utils.parseaddr(msg["From"])[1]
                            process_research_email(query, msg, sender_email)
                        elif any(keyword in subject_lower for keyword in ["calendar", "schedule", "appointment"]):
                            print(f"  -> Routing to Calendar Agent")
                            process_calendar_email(msg, subject)
                        else:
                            print(f"  -> Subject does not match known intents. Skipping.")

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

def send_email(to_address, subject, body):
    """Send an email via SMTP."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_address, msg.as_string())

        print(f"Email sent to {to_address}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def process_research_email(query, msg, sender_email):
    """Research a topic using Gemini and email the response."""
    if not gemini_client:
        print("Error: GEMINI_API_KEY not configured")
        return

    # Also include email body as additional context
    body_context = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                body_context = part.get_payload(decode=True).decode()
                break
    else:
        body_context = msg.get_payload(decode=True).decode()

    print(f"Researching: {query}")

    prompt = f"""You are a research assistant. Answer the following query thoroughly and concisely.

Query: {query}

{"Additional context from email body: " + body_context if body_context.strip() else ""}

Provide a well-structured response with key facts and insights."""

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt]
        )

        result = response.text
        print(f"Research complete, sending response...")

        send_email(
            to_address=sender_email,
            subject=f"Re: Research: {query}",
            body=result
        )
    except Exception as e:
        print(f"Research error: {e}")
        send_email(
            to_address=sender_email,
            subject=f"Re: Research: {query}",
            body=f"Sorry, I encountered an error while researching: {e}"
        )

def main():
    print(f"Email Poller Started (Interval: {POLL_INTERVAL}s)...")
    INPUT_DIR.mkdir(exist_ok=True)
    
    while True:
        process_email()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
