import os
import imaplib
import email
from typing import List
import openai
import re

import weave
from config import InterestConfig, DEFAULT_CONFIG
from interface import EmailMessage, EmailAnalysis, MailHandler
from util import parse_email_message

# weave.init("recruiter-email-bot")


class IMAPMailHandler(MailHandler):
    """IMAP implementation of MailHandler."""

    def __init__(
        self, email_address: str, password: str, server: str = "imap.gmail.com"
    ):
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

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        in_reply_to: str = None,
        references: str = None,
    ) -> None:
        """Create a draft email message in Gmail's Drafts folder."""
        if not self.mail:
            raise ConnectionError("Not connected to mail server")

        # Create the email message
        msg = email.message.EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"] = self.email_address
        msg["To"] = to
        msg["Date"] = email.utils.formatdate(localtime=True)

        # Add threading headers if this is a reply
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        # Convert the message to bytes
        email_bytes = msg.as_bytes()

        try:
            # Select the Gmail Drafts folder
            status, _ = self.mail.select('"[Gmail]/Drafts"')
            if status != "OK":
                # Try alternative folder name
                status, _ = self.mail.select('"[Google Mail]/Drafts"')
                if status != "OK":
                    raise Exception("Failed to select Drafts folder")

            # Append the message to the Drafts folder
            status, _ = self.mail.append(
                '"[Gmail]/Drafts"' if status == "OK" else '"[Google Mail]/Drafts"',
                "(\Draft)",
                None,
                email_bytes,
            )
            if status != "OK":
                raise Exception("Failed to create draft message")

        except Exception as e:
            raise Exception(f"Failed to create draft: {str(e)}")

        # Reselect inbox
        self.get_inbox()


class MailClient:
    def __init__(
        self, mail_handler: MailHandler, config: InterestConfig = DEFAULT_CONFIG
    ):
        """Initialize mail client with a mail handler and configuration."""
        self.mail_handler = mail_handler
        self.openai_client = openai.OpenAI()
        self.config: InterestConfig = config

    def connect(self) -> None:
        """Connect to the mail server."""
        self.mail_handler.connect()

    def disconnect(self) -> None:
        """Safely disconnect from the mail server."""
        self.mail_handler.disconnect()

    @weave.op
    def process_recruiter_emails(self) -> None:
        """
        Main method to process recruiter emails:
        1. Get unread messages
        2. Analyze emails for recruiter content and configured topics
        3. Generate and save response drafts for review
        """
        try:
            self.connect()
            unread_messages = self.get_unread_messages()

            for msg in unread_messages:
                analysis = self.analyze_email(msg)
                if analysis.is_followup:
                    # never respond to follow up emails
                    continue
                if analysis.is_recruiter and not analysis.mentions_topics:
                    response = self.generate_response(msg)
                    self.create_response_draft(msg, response)
                    print(f"Created draft response for: {msg.subject}")

        finally:
            self.disconnect()

    @weave.op
    def get_unread_messages(self, limit: int = 10) -> List[EmailMessage]:
        """Fetch unread messages from the inbox."""
        self.mail_handler.get_inbox()
        message_ids = self.mail_handler.search_unread()
        email_messages = []

        for msg_id in message_ids[:limit]:
            msg = self.mail_handler.fetch_message(msg_id)
            email_messages.append(parse_email_message(msg))

        return email_messages

    def clean_email_content(self, content: str) -> str:
        """
        Clean email content by removing unnecessary elements that don't add value for LLM analysis.
        """
        # Convert multiple newlines to a single newline
        content = re.sub(r"\n\s*\n", "\n", content)

        # Remove URLs and links
        content = re.sub(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            "",
            content,
        )
        content = re.sub(r"<[^>]+>", "", content)  # Remove HTML tags

        # Remove common email disclaimer patterns
        content = re.sub(
            r"CONFIDENTIAL[^\n]*\n[\s\S]*$", "", content, flags=re.IGNORECASE
        )
        content = re.sub(
            r"DISCLAIMER[^\n]*\n[\s\S]*$", "", content, flags=re.IGNORECASE
        )
        content = re.sub(
            r"Privileged/Confidential Information[^\n]*\n[\s\S]*$",
            "",
            content,
            flags=re.IGNORECASE,
        )

        # Remove quoted email chains
        content = re.sub(r"On.*wrote:[\s\S]*$", "", content)  # Remove quoted email
        content = re.sub(
            r"From:.*Sent:.*To:.*Subject:[\s\S]*$", "", content
        )  # Remove forwarded email headers

        # Remove extra whitespace
        content = re.sub(r"\s+", " ", content)
        content = re.sub(r"^\s+|\s+$", "", content, flags=re.MULTILINE)

        return content.strip()

    @weave.op
    def analyze_email(self, email_msg: EmailMessage) -> EmailAnalysis:
        """
        Use LLM to analyze if the email is from a recruiter and if it mentions configured topics of interest.
        Returns an EmailAnalysis object with boolean flags and explanations.
        """
        # Clean the email content before analysis
        clean_subject = self.clean_email_content(email_msg.subject)
        clean_body = self.clean_email_content(email_msg.body)

        topics_str = ", ".join(self.config.topics_of_interest)
        prompt = f"""
        Analyze this email and answer the following questions:
        1. Is this from a recruiter or about a job opportunity?
        2. Does it mention any of these topics in a meaningful way (be strict): {topics_str}
        3. Is this a follow up email? (hint: look for 'Re:' in the subject)

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
                {
                    "role": "system",
                    "content": "You are a helpful assistant that analyzes emails. Provide your analysis in a structured format.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=EmailAnalysis,
        )

        return response.choices[0].message.parsed

    @weave.op
    def generate_response(self, email_msg: EmailMessage) -> str:
        """
        Generate a personalized response to a recruiter email.
        """
        looking_status = (
            "actively looking for"
            if self.config.currently_looking
            else "not currently looking for"
        )

        prompt = f"""
        Generate a polite and personalized response to this recruiter email. Lets make sure to keep it
        casual and friendly, i don't want to come across as too formal or robotic.
        The response should:
        1. Thank them for reaching out
        2. Acknowledge the specific role/company they mentioned
        3. Explain that you're {looking_status} new opportunities
        4. Mention your focus on {self.config.topic_description}, 
            only interested in roles that align with this
        5. My name (for signature): {self.config.name}

        Original email:
        Subject: {email_msg.subject}
        From: {email_msg.sender}
        Body: {email_msg.body}
        """

        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            temperature=1.2,  # bit more creative
            messages=[
                {
                    "role": "system",
                    "content": "You are an assistant that drafts professional but casual email responses.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        return response.choices[0].message.content.strip()

    @weave.op
    def create_response_draft(
        self, email_msg: EmailMessage, response_body: str
    ) -> None:
        """
        Create a draft response to an email.

        Args:
            email_msg: The original email message being responded to
            response_body: The generated response body
        """
        # Extract the sender's email address from the From field
        # The From field might be in the format "Name <email@example.com>"
        sender_match = re.search(r"<(.+?)>", email_msg.sender)
        if sender_match:
            to_address = sender_match.group(1)
        else:
            to_address = email_msg.sender.strip()

        # Create subject with Re: prefix if it doesn't already have one
        subject = email_msg.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Format the response with the original message quoted
        formatted_date = email_msg.date.strftime("%a, %b %d, %Y at %I:%M %p")

        response_body = response_body.replace("\n", "<br>")

        # Create both HTML and plain text versions
        html_response = f"""
        <div>{response_body}</div>
        """

        # Add byline with proper HTML formatting
        html_response += """
        <br><br>
        <div style='font-style: italic; color: #666; font-size: 0.9em;'>
            (composed by Griffin's automated <a href="https://github.com/gtarpenning/nlfw" style="color: #666; text-decoration: underline;">nlfw</a> assistant)
        </div>
        """

        # Quote the original message
        html_response += f"""
        <br><br>
        On {formatted_date}, {email_msg.sender} wrote:<br><br>
        """
        quoted_body = "\n".join(
            f"> {line}" for line in email_msg.body.strip().split("\n")
        )
        quoted_body_html = quoted_body.replace("\n", "<br>")
        html_response += f'<div style="margin-left: 10px; padding-left: 10px; border-left: 1px solid #ccc;">{quoted_body_html}</div>'

        # Create the email message with HTML content
        msg = email.message.EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.mail_handler.email_address
        msg["To"] = to_address
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["In-Reply-To"] = email_msg.message_id
        msg["References"] = email_msg.message_id

        # Set the HTML content
        msg.add_alternative(html_response, subtype="html")

        # Convert the message to bytes and create the draft
        email_bytes = msg.as_bytes()

        try:
            # Select the Gmail Drafts folder
            status, _ = self.mail_handler.mail.select('"[Gmail]/Drafts"')
            if status != "OK":
                # Try alternative folder name
                status, _ = self.mail_handler.mail.select('"[Google Mail]/Drafts"')
                if status != "OK":
                    raise Exception("Failed to select Drafts folder")

            # Append the message to the Drafts folder
            status, _ = self.mail_handler.mail.append(
                '"[Gmail]/Drafts"' if status == "OK" else '"[Google Mail]/Drafts"',
                "(\Draft)",
                None,
                email_bytes,
            )
            if status != "OK":
                raise Exception("Failed to create draft message")

        except Exception as e:
            raise Exception(f"Failed to create draft: {str(e)}")

        # Reselect inbox
        self.mail_handler.get_inbox()


def main_test():
    password = os.getenv("GMAIL_PASSWORD")
    if not password:
        raise ValueError("GMAIL_PASSWORD is not set")
    email = os.getenv("GMAIL_EMAIL")
    if not email:
        raise ValueError("GMAIL_EMAIL is not set")

    mail_handler = IMAPMailHandler(email_address=email, password=password)
    mail_handler.connect()
    mail_client = MailClient(mail_handler=mail_handler)
    unread_messages = mail_client.get_unread_messages()
    analysis = mail_client.analyze_email(unread_messages[0])
    print(analysis)
    response = mail_client.generate_response(unread_messages[0])
    mail_client.create_response_draft(unread_messages[0], response)


if __name__ == "__main__":
    main_test()
