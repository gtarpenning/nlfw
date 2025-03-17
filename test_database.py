import pytest
import os
from datetime import datetime
import json
from database import DatabaseManager, JobEmailData
import sqlite3

TEST_DB_PATH = "test_email_jobs.db"


@pytest.fixture
def test_db():
    """Create a test database instance that uses a temporary file."""
    db = DatabaseManager(db_path=TEST_DB_PATH)
    yield db
    # Cleanup: remove test database after tests
    try:
        os.remove(TEST_DB_PATH)
    except OSError:
        pass


@pytest.fixture
def sample_email_data():
    """Create a sample email data for testing."""
    return JobEmailData(
        message_id="<test123@example.com>",
        sender="recruiter@company.com",
        subject="Software Engineer Position",
        body="We have an exciting opportunity...",
        received_date=datetime.now(),
        analyzed_data={
            "company_name": "TechCorp",
            "role_title": "Senior Software Engineer",
            "job_type": "Full-time",
            "location": "Remote",
            "salary_range": "$150k-$200k",
            "required_experience": "5+ years",
            "technologies": ["Python", "React", "AWS"],
            "recruiter_name": "John Doe",
            "application_deadline": None,
        },
        is_recruiter=True,
        is_followup=False,
        mentions_topics=True,
    )


def test_init_db(test_db):
    """Test database initialization."""
    # Verify the database file was created
    assert os.path.exists(test_db.db_path)

    # Verify table structure
    with sqlite3.connect(test_db.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='job_emails'
        """
        )
        assert cursor.fetchone() is not None


def test_store_and_retrieve_email(test_db, sample_email_data):
    """Test storing and retrieving an email."""
    # Store the email
    test_db.store_email(sample_email_data)

    # Retrieve the email
    retrieved = test_db.get_email(sample_email_data.message_id)

    # Verify all fields match
    assert retrieved is not None
    assert retrieved.message_id == sample_email_data.message_id
    assert retrieved.sender == sample_email_data.sender
    assert retrieved.subject == sample_email_data.subject
    assert retrieved.body == sample_email_data.body
    assert retrieved.is_recruiter == sample_email_data.is_recruiter
    assert retrieved.is_followup == sample_email_data.is_followup
    assert retrieved.mentions_topics == sample_email_data.mentions_topics
    assert retrieved.analyzed_data == sample_email_data.analyzed_data


def test_get_nonexistent_email(test_db):
    """Test retrieving a non-existent email."""
    result = test_db.get_email("nonexistent@example.com")
    assert result is None


def test_get_all_recruiter_emails(test_db):
    """Test retrieving all recruiter emails."""
    # Create multiple test emails
    emails = [
        JobEmailData(
            message_id=f"<test{i}@example.com>",
            sender=f"recruiter{i}@company.com",
            subject=f"Position {i}",
            body=f"Description {i}",
            received_date=datetime.now(),
            analyzed_data={"company_name": f"Company{i}"},
            is_recruiter=True,
            is_followup=False,
            mentions_topics=False,
        )
        for i in range(3)
    ]

    # Add one non-recruiter email
    non_recruiter = JobEmailData(
        message_id="<nonrecruiter@example.com>",
        sender="regular@company.com",
        subject="Regular Email",
        body="Regular content",
        received_date=datetime.now(),
        analyzed_data={},
        is_recruiter=False,
        is_followup=False,
        mentions_topics=False,
    )

    # Store all emails
    for email in emails + [non_recruiter]:
        test_db.store_email(email)

    # Retrieve recruiter emails
    recruiter_emails = test_db.get_all_recruiter_emails()

    # Verify results
    assert len(recruiter_emails) == 3
    assert all(email.is_recruiter for email in recruiter_emails)
    assert all(email.message_id.startswith("<test") for email in recruiter_emails)


def test_extract_job_details(test_db):
    """Test job details extraction from email content."""
    email_body = """
    Hello!
    
    I'm reaching out about a Senior Software Engineer position at TechCorp.
    This is a full-time role with a salary range of $150k-$200k.
    We're looking for someone with 5+ years of experience in Python, React, and AWS.
    
    The position is fully remote.
    
    Please let me know if you're interested!
    
    Best regards,
    John Doe
    Technical Recruiter
    """

    subject = "Senior Software Engineer Position at TechCorp"

    details = test_db.extract_job_details(email_body, subject)

    # Verify extracted information
    assert isinstance(details, dict)
    assert details.get("company_name") == "TechCorp"
    assert "Senior Software Engineer" in details.get("role_title", "")
    assert details.get("job_type") == "full-time"
    assert "remote" in details.get("location", "").lower()
    assert any(
        tech in details.get("technologies", []) for tech in ["Python", "React", "AWS"]
    )
    assert "John Doe" in details.get("recruiter_name", "")


def test_update_existing_email(test_db, sample_email_data):
    """Test updating an existing email record."""
    # Store initial email
    test_db.store_email(sample_email_data)

    # Modify the email data
    updated_data = sample_email_data
    updated_data.subject = "Updated Subject"
    updated_data.analyzed_data["salary_range"] = "$160k-$210k"

    # Store updated email
    test_db.store_email(updated_data)

    # Retrieve and verify
    retrieved = test_db.get_email(sample_email_data.message_id)
    assert retrieved.subject == "Updated Subject"
    assert retrieved.analyzed_data["salary_range"] == "$160k-$210k"

    # Verify only one record exists
    all_recruiter_emails = test_db.get_all_recruiter_emails()
    assert len(all_recruiter_emails) == 1
