import asyncio
import os
import imaplib
import email
from email.header import decode_header
from typing import Dict, List, Optional, Tuple, NamedTuple, Protocol, Any
from dataclasses import dataclass
import openai
from datetime import datetime
from email.utils import parsedate_to_datetime
from abc import ABC, abstractmethod
import re
from pydantic import BaseModel

import weave

# weave.init("recruiter-email-bot")

@dataclass
class EmailMessage:
    subject: str
    sender: str
    body: str
    date: datetime
    message_id: str

class EmailAnalysis(BaseModel):
    is_recruiter: bool
    mentions_climate: bool
    recruiter_explanation: str
    climate_explanation: str

class MailHandler(ABC):
    """Abstract interface for mail operations."""
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to mail server."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to mail server."""
        pass
    
    @abstractmethod
    def get_inbox(self) -> None:
        """Select the inbox folder."""
        pass
    
    @abstractmethod
    def search_unread(self) -> List[str]:
        """Search for unread message IDs."""
        pass
    
    @abstractmethod
    def fetch_message(self, msg_id: str) -> email.message.Message:
        """Fetch a specific message by ID."""
        pass
    
    @abstractmethod
    def mark_as_read(self, msg_id: str) -> None:
        """Mark a message as read."""
        pass
    
    @abstractmethod
    def mark_as_unread(self, msg_id: str) -> None:
        """Mark a message as unread."""
        pass

class IMAPMailHandler(MailHandler):
    """IMAP implementation of MailHandler."""
    
    def __init__(self, email_address: str, password: str, server: str = "imap.gmail.com"):
        self.email_address = email_address
        self.password = password
        self.server = server
        self.mail = None

    def connect(self) -> None:
        try:
            self.mail = imaplib.IMAP4_SSL(self.server)
            self.mail.login(self.email_address, self.password)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to mail server: {str(e)}")

    def disconnect(self) -> None:
        if self.mail:
            try:
                self.mail.close()
                self.mail.logout()
            except:
                pass

    def get_inbox(self) -> None:
        if not self.mail:
            raise ConnectionError("Not connected to mail server")
        status, _ = self.mail.select("INBOX")
        if status != "OK":
            raise Exception("Failed to select inbox")

    def search_unread(self) -> List[str]:
        if not self.mail:
            raise ConnectionError("Not connected to mail server")
        status, messages = self.mail.search(None, "UNSEEN")
        if status != "OK":
            raise Exception("Failed to search for unread messages")
        return messages[0].split()

    def fetch_message(self, msg_id: str) -> email.message.Message:
        if not self.mail:
            raise ConnectionError("Not connected to mail server")
        status, msg_data = self.mail.fetch(msg_id, "(RFC822)")
        if status != "OK":
            raise Exception(f"Failed to fetch message {msg_id}")
        email_body = msg_data[0][1]
        return email.message_from_bytes(email_body)
    
    def mark_as_read(self, msg_id: str) -> None:
        if not self.mail:
            raise ConnectionError("Not connected to mail server")
        status, _ = self.mail.store(msg_id, "+FLAGS", "(\Seen)")
        if status != "OK":
            raise Exception(f"Failed to mark message {msg_id} as read")

    def mark_as_unread(self, msg_id: str) -> None:
        if not self.mail:
            raise ConnectionError("Not connected to mail server")
        status, _ = self.mail.store(msg_id, "-FLAGS", "(\Seen)")
        if status != "OK":
            raise Exception(f"Failed to mark message {msg_id} as unread")

class MailClient:
    def __init__(self, mail_handler: MailHandler):
        """Initialize mail client with a mail handler."""
        self.mail_handler = mail_handler
        self.openai_client = openai.OpenAI()

    def connect(self) -> None:
        """Connect to the mail server."""
        self.mail_handler.connect()

    def disconnect(self) -> None:
        """Safely disconnect from the mail server."""
        self.mail_handler.disconnect()

    def _parse_email_message(self, msg: email.message.Message) -> EmailMessage:
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
                    "%Y-%m-%d %H:%M:%S %z",      # ISO-like format
                    "%d %b %Y %H:%M:%S %z",      # Without weekday
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
            message_id=msg["message-id"] or ""
        )

    @weave.op
    def get_unread_messages(self, limit: int = 10) -> List[EmailMessage]:
        """Fetch unread messages from the inbox."""
        self.mail_handler.get_inbox()
        message_ids = self.mail_handler.search_unread()
        email_messages = []
        
        for msg_id in message_ids[:limit]:
            msg = self.mail_handler.fetch_message(msg_id)
            email_messages.append(self._parse_email_message(msg))
            # Mark as read after processing
            # self.mail_handler.mark_as_read(msg_id)
            self.mail_handler.mark_as_unread(msg_id)
            
        return email_messages

    def clean_email_content(self, content: str) -> str:
        """
        Clean email content by removing unnecessary elements that don't add value for LLM analysis.
        """
        # Convert multiple newlines to a single newline
        content = re.sub(r'\n\s*\n', '\n', content)

        # Remove URLs and links
        content = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', content)
        content = re.sub(r'<[^>]+>', '', content)  # Remove HTML tags
        
        # Remove common email disclaimer patterns
        content = re.sub(r'CONFIDENTIAL[^\n]*\n[\s\S]*$', '', content, flags=re.IGNORECASE)
        content = re.sub(r'DISCLAIMER[^\n]*\n[\s\S]*$', '', content, flags=re.IGNORECASE)
        content = re.sub(r'Privileged/Confidential Information[^\n]*\n[\s\S]*$', '', content, flags=re.IGNORECASE)
        
        # Remove quoted email chains
        content = re.sub(r'On.*wrote:[\s\S]*$', '', content)  # Remove quoted email
        content = re.sub(r'From:.*Sent:.*To:.*Subject:[\s\S]*$', '', content)  # Remove forwarded email headers
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'^\s+|\s+$', '', content, flags=re.MULTILINE)
        
        return content.strip()

    @weave.op
    def analyze_email(self, email_msg: EmailMessage) -> EmailAnalysis:
        """
        Use LLM to analyze if the email is from a recruiter and if it mentions climate change.
        Returns an EmailAnalysis object with boolean flags and explanations.
        """
        # Clean the email content before analysis
        clean_subject = self.clean_email_content(email_msg.subject)
        clean_body = self.clean_email_content(email_msg.body)
        
        prompt = f"""
        Analyze this email and answer the following questions:
        1. Is this from a recruiter or about a job opportunity, and is it the first email they have sent (False if this is a follow up or reply)?
        2. Does it mention climate change, environmental impact, or sustainability in any meaningful way (be strict)?

        For each question, provide:
        - A boolean answer (true/false)
        - A brief explanation of why you made that determination

        Subject: {clean_subject}
        From: {email_msg.sender}
        Body: {clean_body}
        """

        response = self.openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes emails. Provide your analysis in a structured format."},
                {"role": "user", "content": prompt}
            ],
            response_format=EmailAnalysis
        )
        
        return response.choices[0].message.parsed

    @weave.op
    async def generate_response(self, email_msg: EmailMessage) -> str:
        """
        Generate a personalized response to a recruiter email.
        """
        prompt = f"""
        Generate a polite and personalized response to this recruiter email.
        The response should:
        1. Thank them for reaching out
        2. Acknowledge the specific role/company they mentioned
        3. Explain that you're not currently looking for new opportunities
        4. Mention your focus on climate change and environmental impact, 
            only interesting in roles that align with this

        Original email:
        Subject: {email_msg.subject}
        From: {email_msg.sender}
        Body: {email_msg.body}
        """

        response = await self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that drafts professional email responses."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response.choices[0].message.content.strip()

    @weave.op
    async def process_recruiter_emails(self) -> None:
        """
        Main method to process recruiter emails:
        1. Get unread messages
        2. Analyze emails for recruiter content and climate mentions
        3. Generate and send responses as needed
        """
        try:
            self.connect()
            unread_messages = self.get_unread_messages()
            
            for msg in unread_messages:
                analysis = await self.analyze_email(msg)
                if analysis.is_recruiter and not analysis.mentions_climate:
                    response = await self.generate_response(msg)
                    # TODO: Implement send_response method
                    print(f"Generated response for {msg.subject}:\n{response}\n")
                
        finally:
            self.disconnect()

if __name__ == "__main__":
    password = os.getenv("GMAIL_PASSWORD")
    if not password:
        raise ValueError("GMAIL_PASSWORD is not set")
    email = os.getenv("GMAIL_EMAIL")
    if not email:
        raise ValueError("GMAIL_EMAIL is not set")
    mail_handler = IMAPMailHandler(
        email_address=email,
        password=password
    )
    mail_handler.connect()
    mail_client = MailClient(mail_handler=mail_handler)
    unread_messages = mail_client.get_unread_messages()
    print(unread_messages)
    analysis = mail_client.analyze_email(unread_messages[0])
    print(analysis)