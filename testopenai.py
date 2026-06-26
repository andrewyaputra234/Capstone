"""Manual OpenAI environment verification helper.

This file is intentionally named as it was originally, but it must not perform
network calls during ``python -m unittest discover``. Run it directly when you
want to check the local `.env` setup:

    python testopenai.py
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI


def main() -> int:
    """Verify that OPENAI_API_KEY is loaded and can make a tiny request."""
    load_dotenv()

    try:
        print("Reading .env and testing OpenAI connection...")

        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("Could not find OPENAI_API_KEY. Is your .env file in the right folder?")

        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'Environment key is working!'"}],
            max_tokens=15,
        )

        print("\nSuccess! OpenAI responded:")
        print(response.choices[0].message.content)
        return 0
    except Exception as error:
        print("\nVerification failed.")
        print(f"Error details: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
