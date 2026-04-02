"""
Agent A4: Avatar/TTS Agent
- Converts assessment text (questions, feedback, etc.) to speech audio (WAV)
- Uses pyttsx3 for offline, dependency-free text-to-speech
"""

import sys
from pathlib import Path
from argparse import ArgumentParser

def tts_pyttsx3(text: str, output_path: Path):
    """Convert text to speech using pyttsx3 and save as WAV."""
    try:
        import pyttsx3
    except ImportError:
        print("ERROR: pyttsx3 not installed. Run: pip install pyttsx3")
        sys.exit(1)
    
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  # Slow speech for clarity
    engine.save_to_file(text, str(output_path))
    engine.runAndWait()
    print(f"SUCCESS: Audio saved to {output_path}")

def main():
    parser = ArgumentParser(description="Agent A4: Avatar/TTS - Convert text to speech audio.")
    parser.add_argument("--text", type=str, required=True, help="Text to convert to speech.")
    parser.add_argument("--output", type=str, default="output.wav", help="Output audio file path (WAV)")
    args = parser.parse_args()

    text = args.text.strip()
    if not text:
        print("ERROR: No text provided.")
        sys.exit(1)
    output_path = Path(args.output)
    tts_pyttsx3(text, output_path)

if __name__ == "__main__":
    main()
