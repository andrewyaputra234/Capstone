import os
from dotenv import load_dotenv
from openai import OpenAI

# 1. Load the variables from the .env file into your system environment
load_dotenv()

# 2. Initialize the client (it will now successfully find OPENAI_API_KEY)
client = OpenAI()

try:
    print("🔄 Reading .env and testing OpenAI connection...")
    
    # Check if the key was actually loaded first
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Could not find OPENAI_API_KEY. Is your .env file in the right folder?")

    # 3. Make a tiny test request
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say 'Environment key is working!'"}],
        max_tokens=15
    )
    
    print("\n✅ Success! OpenAI responded:")
    print(response.choices[0].message.content)

except Exception as e:
    print("\n❌ Verification Failed!")
    print(f"Error details: {e}")