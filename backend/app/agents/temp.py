from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
client = OpenAI()  # now works, since env var exists

response = client.responses.create(
    model="gpt-4o",
    input="Write a one-sentence bedtime story about a unicorn."
)

print(response.output_text)