from langchain_openai import ChatOpenAI
from browser_use import Agent
import asyncio

test_site = "https://www.clay.com/"


personal_data = {
    "name": "Griffin Tarpenning",
    "email": "gtarpenning@gmail.com",
    "phone": "6504741567",
    "address": "75 Tum Suden Way, Woodside, CA 94062",
}

task = f"""
DATA: {personal_data}

LINK: {test_site}

INSTRUCTIONS:
- Search the page for the link to unsubscribe, or "do not sell my data" (normally at BOTTOM in footer)
- Click the link
- Fill in the form with the data provided
"""


async def main():
    agent = Agent(
        task=task,
        llm=ChatOpenAI(model="gpt-4o"),
    )
    await agent.run()


asyncio.run(main())
