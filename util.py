from email.header import decode_header
from email.utils import parsedate_to_datetime
from email.message import Message
from datetime import datetime

from mail import EmailMessage


def parse_email_message(msg: Message) -> EmailMessage:
    """Parse email message into our internal format."""
    subject = ""
    if msg["subject"]:
        subject = decode_header(msg["subject"])[0][0]
        if isinstance(subject, bytes):
            subject = subject.decode()

    sender = msg["from"] if msg["from"] else ""

    # More robust date parsing
    date = datetime.now()
    if msg["date"]:
        try:
            # First try email.utils parser which handles most email date formats
            date = parsedate_to_datetime(msg["date"])
        except (TypeError, ValueError):
            # Fallback to common format patterns
            date_str = msg["date"]
            formats = [
                "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822
                "%a, %d %b %Y %H:%M:%S %Z",  # With timezone name
                "%a, %d %b %Y %H:%M:%S GMT",  # Specific GMT format
                "%Y-%m-%d %H:%M:%S %z",  # ISO-like format
                "%d %b %Y %H:%M:%S %z",  # Without weekday
            ]

            for fmt in formats:
                try:
                    date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

    # Get email body
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode()
                    break
                except:
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode()
        except:
            body = msg.get_payload()

    return EmailMessage(
        subject=subject,
        sender=sender,
        body=body,
        date=date,
        message_id=msg["message-id"] or "",
    )
