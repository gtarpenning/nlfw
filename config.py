from typing import List
from pydantic import BaseModel


class InterestConfig(BaseModel):
    topics_of_interest: List[str]
    topic_description: str  # Used in response generation to describe what kind of roles you're interested in
    currently_looking: bool = False  # Whether you're actively looking for opportunities
    name: str


# Default configuration
DEFAULT_CONFIG = InterestConfig(
    topics_of_interest=["climate change", "sustainability", "environmental impact"],
    topic_description="roles focused on climate change and environmental impact",
    currently_looking=False,
    name="Griffin Tarpenning",
)
