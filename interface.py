from dataclasses import dataclass
from datetime import datetime
from abc import ABC, abstractmethod
from typing import List
from pydantic import BaseModel
from email.message import Message


@dataclass
class EmailMessage:
    subject: str
    sender: str
    body: str
    date: datetime
    message_id: str


class EmailAnalysis(BaseModel):
    is_recruiter: bool
    mentions_topics: bool
    recruiter_explanation: str
    topic_explanation: str


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
    def fetch_message(self, msg_id: str) -> Message:
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

    @abstractmethod
    def create_draft(self, to: str, subject: str, body: str) -> None:
        """Create a draft email message."""
        pass
