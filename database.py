import sqlite3
import json
from typing import Dict, Optional
from dataclasses import dataclass
import openai
from datetime import datetime


@dataclass
class JobEmailData:
    message_id: str
    sender: str
    subject: str
    body: str
    received_date: datetime
    analyzed_data: Dict
    is_recruiter: bool
    is_followup: bool
    mentions_topics: bool


class DatabaseManager:
    def __init__(self, db_path: str = "email_jobs.db"):
        self.db_path = db_path
        self.openai_client = openai.OpenAI()
        self.init_db()

    def init_db(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS job_emails (
                    message_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    received_date TIMESTAMP NOT NULL,
                    analyzed_data JSON NOT NULL,
                    is_recruiter BOOLEAN NOT NULL,
                    is_followup BOOLEAN NOT NULL,
                    mentions_topics BOOLEAN NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

    def extract_job_details(self, email_body: str, subject: str) -> Dict:
        """Use LLM to extract structured information from the email."""
        prompt = f"""
        Extract the following information from this job-related email into a JSON format: 
        - company_name: The name of the company
        - role_title: The specific job title/role mentioned
        - job_type: The type of role (full-time, contract, etc.)
        - location: Work location or remote status
        - salary_range: Any mentioned salary range (if provided)
        - required_experience: Years or level of experience required
        - technologies: List of specific technologies or skills mentioned
        - recruiter_name: Name of the recruiter
        - application_deadline: Any mentioned deadline (if provided)
        
        Subject: {subject}
        Body: {email_body}

        Return only the JSON object with these fields. Use null for missing information.
        """

        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts structured job information from emails. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    def store_email(self, email_data: JobEmailData) -> None:
        """Store email and its analysis in the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO job_emails (
                    message_id, sender, subject, body, received_date,
                    analyzed_data, is_recruiter, is_followup, mentions_topics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    email_data.message_id,
                    email_data.sender,
                    email_data.subject,
                    email_data.body,
                    email_data.received_date.isoformat(),
                    json.dumps(email_data.analyzed_data),
                    email_data.is_recruiter,
                    email_data.is_followup,
                    email_data.mentions_topics,
                ),
            )
            conn.commit()

    def get_email(self, message_id: str) -> Optional[JobEmailData]:
        """Retrieve an email by its message ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM job_emails WHERE message_id = ?
            """,
                (message_id,),
            )
            row = cursor.fetchone()

            if row:
                return JobEmailData(
                    message_id=row["message_id"],
                    sender=row["sender"],
                    subject=row["subject"],
                    body=row["body"],
                    received_date=datetime.fromisoformat(row["received_date"]),
                    analyzed_data=json.loads(row["analyzed_data"]),
                    is_recruiter=bool(row["is_recruiter"]),
                    is_followup=bool(row["is_followup"]),
                    mentions_topics=bool(row["mentions_topics"]),
                )
            return None

    def get_all_recruiter_emails(self) -> list[JobEmailData]:
        """Retrieve all recruiter emails."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM job_emails 
                WHERE is_recruiter = 1 
                ORDER BY received_date DESC
            """
            )

            return [
                JobEmailData(
                    message_id=row["message_id"],
                    sender=row["sender"],
                    subject=row["subject"],
                    body=row["body"],
                    received_date=datetime.fromisoformat(row["received_date"]),
                    analyzed_data=json.loads(row["analyzed_data"]),
                    is_recruiter=bool(row["is_recruiter"]),
                    is_followup=bool(row["is_followup"]),
                    mentions_topics=bool(row["mentions_topics"]),
                )
                for row in cursor.fetchall()
            ]
