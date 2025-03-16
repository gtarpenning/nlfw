import pytest
import email
from email.message import EmailMessage as RawEmailMessage
from datetime import datetime
from typing import List
from mail import MailHandler, MailClient, EmailMessage, EmailAnalysis
from pydantic import BaseModel

class MockMailHandler(MailHandler):
    def __init__(self, test_messages: List[RawEmailMessage]):
        self.test_messages = test_messages
        self.is_connected = False
        self.inbox_selected = False
        self.read_messages = set()  # Track which messages are marked as read

    def connect(self) -> None:
        self.is_connected = True

    def disconnect(self) -> None:
        self.is_connected = False
        self.inbox_selected = False

    def get_inbox(self) -> None:
        if not self.is_connected:
            raise ConnectionError("Not connected")
        self.inbox_selected = True

    def search_unread(self) -> List[str]:
        if not self.is_connected:
            raise ConnectionError("Not connected")
        if not self.inbox_selected:
            raise RuntimeError("Inbox not selected")
        # Only return IDs of unread messages
        return [str(i) for i in range(len(self.test_messages)) if str(i) not in self.read_messages]

    def fetch_message(self, msg_id: str) -> RawEmailMessage:
        if not self.is_connected:
            raise ConnectionError("Not connected")
        if not self.inbox_selected:
            raise RuntimeError("Inbox not selected")
        return self.test_messages[int(msg_id)]
    
    def mark_as_read(self, msg_id: str) -> None:
        if not self.is_connected:
            raise ConnectionError("Not connected")
        if not self.inbox_selected:
            raise RuntimeError("Inbox not selected")
        self.read_messages.add(msg_id)

    def mark_as_unread(self, msg_id: str) -> None:
        if not self.is_connected:
            raise ConnectionError("Not connected")
        if not self.inbox_selected:
            raise RuntimeError("Inbox not selected")
        if msg_id in self.read_messages:
            self.read_messages.remove(msg_id)

def create_test_email(subject: str, sender: str, body: str, date_str: str = "Thu, 14 Mar 2024 10:00:00 GMT") -> RawEmailMessage:
    """Helper function to create test email messages."""
    msg = RawEmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = date_str
    msg["Message-ID"] = f"<test_{subject.replace(' ', '_')}@example.com>"
    msg.set_content(body)
    return msg

@pytest.fixture
def test_emails():
    """Create a set of test emails."""
    return [
        # Regular recruiter email
        create_test_email(
            subject="Exciting Software Engineering Opportunity at TechCorp",
            sender="recruiter@techcorp.com",
            body="""
            Hi there,
            
            I hope this email finds you well. I came across your profile and was impressed by your experience.
            We have an exciting Software Engineering position at TechCorp that I think would be perfect for you.
            
            Would you be interested in learning more?
            
            Best regards,
            Jane Recruiter
            """
        ),
        # Recruiter email mentioning climate
        create_test_email(
            subject="Climate Tech Opportunity - Senior Engineer",
            sender="talent@climatecorp.com",
            body="""
            Hello,
            
            I'm reaching out about a Senior Engineer position at ClimateCorp.
            We're working on cutting-edge climate change solutions and environmental technology.
            Your background would be perfect for our mission to reduce carbon emissions.
            
            Would you be interested in discussing this opportunity?
            
            Best,
            John Climate
            """
        ),
        # Non-recruiter email
        create_test_email(
            subject="Team meeting notes",
            sender="colleague@company.com",
            body="""
            Here are the notes from today's team meeting:
            1. Project updates
            2. Sprint planning
            3. Upcoming deadlines
            
            Let me know if you have any questions.
            """
        ),
        # Follow-up recruiter email
        create_test_email(
            subject="Re: Exciting Software Engineering Opportunity at TechCorp",
            sender="recruiter@techcorp.com",
            body="""
            Hi again,
            
            I wanted to follow up on my previous email about the Software Engineering position.
            Have you had a chance to consider the opportunity?
            
            Best regards,
            Jane Recruiter
            """
        )
    ]

@pytest.fixture
def mail_client(test_emails):
    """Create a MailClient with mock handler."""
    handler = MockMailHandler(test_emails)
    return MailClient(handler)

@pytest.mark.asyncio
async def test_get_unread_messages(mail_client, test_emails):
    """Test fetching unread messages."""
    mail_client.connect()
    messages = mail_client.get_unread_messages()
    
    assert len(messages) == len(test_emails)
    assert all(isinstance(msg, EmailMessage) for msg in messages)
    assert messages[0].subject == "Exciting Software Engineering Opportunity at TechCorp"
    
    # Verify messages are marked as read
    assert len(mail_client.mail_handler.read_messages) == len(test_emails)
    assert all(str(i) in mail_client.mail_handler.read_messages for i in range(len(test_emails)))

@pytest.mark.asyncio
async def test_unread_messages_are_marked_as_read(mail_client, test_emails):
    """Test that messages are properly marked as read after processing."""
    mail_client.connect()
    
    # First fetch should get all messages
    messages1 = mail_client.get_unread_messages()
    assert len(messages1) == len(test_emails)
    
    # Second fetch should get no messages (all marked as read)
    messages2 = mail_client.get_unread_messages()
    assert len(messages2) == 0
    
    # Verify all messages are marked as read
    assert len(mail_client.mail_handler.read_messages) == len(test_emails)
    assert all(str(i) in mail_client.mail_handler.read_messages for i in range(len(test_emails)))

@pytest.mark.asyncio
async def test_mark_as_read_requires_connection(mail_client):
    """Test that mark_as_read requires an active connection."""
    with pytest.raises(ConnectionError):
        mail_client.mail_handler.mark_as_read("0")
    
    mail_client.connect()
    mail_client.mail_handler.mark_as_read("0")
    
    mail_client.disconnect()
    with pytest.raises(ConnectionError):
        mail_client.mail_handler.mark_as_read("1")

@pytest.mark.asyncio
async def test_analyze_regular_recruiter_email(mail_client):
    """Test analyzing a regular recruiter email."""
    mail_client.connect()
    messages = mail_client.get_unread_messages()
    analysis = await mail_client.analyze_email(messages[0])
    
    assert isinstance(analysis, EmailAnalysis)
    assert analysis.is_recruiter is True
    assert analysis.mentions_climate is False
    assert isinstance(analysis.recruiter_explanation, str)
    assert len(analysis.recruiter_explanation) > 0
    assert isinstance(analysis.climate_explanation, str)
    assert len(analysis.climate_explanation) > 0
    assert analysis.model_dump()  # Verify Pydantic serialization works

@pytest.mark.asyncio
async def test_analyze_climate_recruiter_email(mail_client):
    """Test analyzing a climate-focused recruiter email."""
    mail_client.connect()
    messages = mail_client.get_unread_messages()
    analysis = await mail_client.analyze_email(messages[1])
    
    assert isinstance(analysis, EmailAnalysis)
    assert analysis.is_recruiter is True
    assert analysis.mentions_climate is True
    assert "climate" in analysis.climate_explanation.lower()
    assert "recruiter" in analysis.recruiter_explanation.lower()
    assert analysis.model_dump()  # Verify Pydantic serialization works

@pytest.mark.asyncio
async def test_analyze_non_recruiter_email(mail_client):
    """Test analyzing a non-recruiter email."""
    mail_client.connect()
    messages = mail_client.get_unread_messages()
    analysis = await mail_client.analyze_email(messages[2])
    
    assert isinstance(analysis, EmailAnalysis)
    assert analysis.is_recruiter is False
    assert analysis.mentions_climate is False
    assert "meeting" in analysis.recruiter_explanation.lower()
    assert "not" in analysis.climate_explanation.lower()
    assert analysis.model_dump()  # Verify Pydantic serialization works

@pytest.mark.asyncio
async def test_analyze_followup_email(mail_client):
    """Test analyzing a follow-up recruiter email."""
    mail_client.connect()
    messages = mail_client.get_unread_messages()
    analysis = await mail_client.analyze_email(messages[3])
    
    assert isinstance(analysis, EmailAnalysis)
    assert analysis.is_recruiter is False  # Should be False because it's a follow-up
    assert analysis.mentions_climate is False
    assert "follow" in analysis.recruiter_explanation.lower()
    assert "not" in analysis.climate_explanation.lower()
    assert analysis.model_dump()  # Verify Pydantic serialization works

@pytest.mark.asyncio
async def test_generate_response(mail_client):
    """Test generating a response to a recruiter email."""
    mail_client.connect()
    messages = mail_client.get_unread_messages()
    response = await mail_client.generate_response(messages[0])
    
    assert isinstance(response, str)
    assert len(response) > 0
    assert "climate" in response.lower()
    assert "thank" in response.lower()

@pytest.mark.asyncio
async def test_connection_state(mail_client):
    """Test connection state handling."""
    # Should raise when not connected
    with pytest.raises(ConnectionError):
        mail_client.mail_handler.get_inbox()
    
    # Should work after connecting
    mail_client.connect()
    mail_client.mail_handler.get_inbox()
    
    # Should raise after disconnecting
    mail_client.disconnect()
    with pytest.raises(ConnectionError):
        mail_client.mail_handler.get_inbox()

@pytest.mark.asyncio
async def test_process_recruiter_emails(mail_client, capsys):
    """Test the main processing function."""
    await mail_client.process_recruiter_emails()
    captured = capsys.readouterr()
    
    # Should only generate response for the first email (regular recruiter email)
    assert "Exciting Software Engineering Opportunity" in captured.out
    assert "Climate Tech Opportunity" not in captured.out  # Climate email should be skipped
    assert "Team meeting notes" not in captured.out  # Non-recruiter email should be skipped
    assert "Re: Exciting Software Engineering" not in captured.out  # Follow-up should be skipped 

def test_clean_email_content(mail_client):
    """Test email content cleaning functionality."""
    test_cases = [
        # Test case 1: Email with signature
        (
            """
            Hi there,
            
            This is a test email.
            
            Best regards,
            John Doe
            Senior Recruiter
            Phone: 123-456-7890
            """,
            "Hi there, This is a test email."
        ),
        
        # Test case 2: Email with URLs and HTML
        (
            """
            Check out our website: https://example.com
            Or click here: <a href="https://test.com">link</a>
            Some normal text.
            """,
            "Check out our website: Or click here: Some normal text."
        ),
        
        # Test case 3: Email with confidentiality notice
        (
            """
            Important message here.
            
            CONFIDENTIAL: This email and any files transmitted with it are confidential.
            If you are not the intended recipient, please delete this email.
            """,
            "Important message here."
        ),
        
        # Test case 4: Email with quoted content
        (
            """
            Sure, I can help with that.

            On Tue, Mar 12, 2024 at 10:00 AM John Doe <john@example.com> wrote:
            > Can you help me with this?
            > Thanks
            """,
            "Sure, I can help with that."
        ),
        
        # Test case 5: Email with meeting details
        (
            """
            Let's have a meeting.
            
            When: Tomorrow at 2 PM
            Where: Conference Room A
            Meeting ID: 123 456 789
            Passcode: abc123
            
            See you there!
            """,
            "Let's have a meeting. See you there!"
        ),
        
        # Test case 6: Email with multiple types of content to clean
        (
            """
            Hi there,
            
            Check our job board: https://jobs.example.com
            
            Best regards,
            John Smith
            
            --
            John Smith | Senior Recruiter
            Tel: +1 234 567 8900
            
            CONFIDENTIAL: This email is confidential.
            """,
            "Hi there, Check our job board:"
        )
    ]
    
    for input_text, expected_output in test_cases:
        cleaned = mail_client.clean_email_content(input_text)
        assert cleaned.strip() == expected_output.strip()

def test_clean_email_preserves_important_content(mail_client):
    """Test that email cleaning preserves important recruiting and climate-related content."""
    email_content = """
    Hi there,
    
    I'm reaching out about an exciting opportunity at our climate tech startup.
    We're working on reducing carbon emissions and fighting climate change.
    
    The role offers:
    - Competitive salary
    - Great benefits
    https://benefits.example.com
    
    Best regards,
    Jane Recruiter
    Senior Technical Recruiter
    """
    
    cleaned = mail_client.clean_email_content(email_content)
    
    # Check that important keywords are preserved
    assert "climate tech" in cleaned
    assert "carbon emissions" in cleaned
    assert "climate change" in cleaned
    assert "opportunity" in cleaned
    assert "role" in cleaned
    assert "salary" in cleaned
    assert "benefits" in cleaned
    
    # Check that unnecessary content is removed
    assert "https://" not in cleaned
    assert "Senior Technical Recruiter" not in cleaned 

@pytest.mark.asyncio
async def test_mark_as_unread_requires_connection(mail_client):
    """Test that mark_as_unread requires an active connection."""
    with pytest.raises(ConnectionError):
        mail_client.mail_handler.mark_as_unread("0")
    
    mail_client.connect()
    mail_client.mail_handler.mark_as_unread("0")
    
    mail_client.disconnect()
    with pytest.raises(ConnectionError):
        mail_client.mail_handler.mark_as_unread("1")

@pytest.mark.asyncio
async def test_mark_as_unread_functionality(mail_client, test_emails):
    """Test marking messages as unread."""
    mail_client.connect()
    
    # First mark some messages as read
    messages1 = mail_client.get_unread_messages()
    assert len(messages1) == len(test_emails)
    
    # Mark a specific message as unread
    mail_client.mail_handler.mark_as_unread("1")
    assert "1" not in mail_client.mail_handler.read_messages
    
    # Fetch messages again - should get the unread one
    messages2 = mail_client.get_unread_messages()
    assert len(messages2) == 1
    assert messages2[0].subject == "Climate Tech Opportunity - Senior Engineer"
    
    # Mark all messages as unread
    for msg_id in range(len(test_emails)):
        mail_client.mail_handler.mark_as_unread(str(msg_id))
    
    # Verify all messages are unread
    assert len(mail_client.mail_handler.read_messages) == 0
    
    # Fetch messages again - should get all messages
    messages3 = mail_client.get_unread_messages()
    assert len(messages3) == len(test_emails) 