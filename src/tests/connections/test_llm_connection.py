import os

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])

message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=20,
    messages=[{"role": "user", "content": "Reply with exactly: LLM connection OK"}],
)

print(message.content[0].text)
