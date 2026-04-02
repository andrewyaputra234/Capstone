"""
Agent Audio Input (ASR)
Handles student audio recording and speech-to-text transcription.

Features:
- Record audio from microphone (WAV format)
- Transcribe using OpenAI Whisper API
- Store audio files with session/turn metadata
"""

import os
import sys
from datetime import datetime
from pathlib import Path
import json

try:
    import pyaudio
    import wave
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class AudioRecorder:
    """Handle audio recording from microphone."""
    
    CHUNK = 1024  # Recording chunk size
    FORMAT = 8  # pyaudio.paInt16, but using int value
    CHANNELS = 1  # Mono
    RATE = 16000  # 16kHz for Whisper
    
    @staticmethod
    def record_audio(duration: int = 10, output_path: str = None) -> str:
        """
        Record audio from microphone.
        
        Args:
            duration: Recording duration in seconds (default 10)
            output_path: Where to save WAV file (default: data/sessions/audio_TIMESTAMP.wav)
        
        Returns:
            Path to saved WAV file
        """
        if not PYAUDIO_AVAILABLE:
            raise RuntimeError("pyaudio not installed. Run: pip install pyaudio")
        
        if output_path is None:
            output_dir = "data/sessions"
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"{output_dir}/audio_{timestamp}.wav"
        
        print(f"\n🎤 Recording for {duration} seconds...")
        print("Press Ctrl+C to stop early.\n")
        
        try:
            p = pyaudio.PyAudio()
            
            stream = p.open(
                format=pyaudio.paInt16,
                channels=AudioRecorder.CHANNELS,
                rate=AudioRecorder.RATE,
                input=True,
                frames_per_buffer=AudioRecorder.CHUNK
            )
            
            frames = []
            
            try:
                for i in range(0, int(AudioRecorder.RATE / AudioRecorder.CHUNK * duration)):
                    data = stream.read(AudioRecorder.CHUNK)
                    frames.append(data)
                    
                    # Progress indicator
                    if (i + 1) % 16 == 0:  # Every ~1 second at 16kHz
                        elapsed = int((i + 1) / 16)
                        print(f"  Recording... {elapsed}s / {duration}s")
            
            except KeyboardInterrupt:
                print("\n✓ Recording stopped by user")
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # Save WAV file
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(AudioRecorder.CHANNELS)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(AudioRecorder.RATE)
                wf.writeframes(b''.join(frames))
            
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"✓ Audio saved: {output_path} ({file_size_mb:.2f} MB)")
            
            return output_path
        
        except Exception as e:
            print(f"ERROR recording audio: {str(e)}")
            raise


class SpeechToText:
    """Handle speech-to-text transcription using OpenAI Whisper."""
    
    def __init__(self):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai not installed. Run: pip install openai")
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.client = OpenAI(api_key=api_key)
    
    def transcribe_audio(self, audio_path: str) -> dict:
        """
        Transcribe audio file using OpenAI Whisper API.
        
        Args:
            audio_path: Path to audio file (WAV, MP3, M4A, MP2, MPEG, MPGA, OGA, OGG, OPUS, FLAC, WEBM)
        
        Returns:
            {
                "text": "transcribed text",
                "duration": duration_in_seconds,
                "confidence": null (not provided by Whisper API)
            }
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        try:
            print(f"\n🔄 Transcribing audio: {os.path.basename(audio_path)}")
            
            with open(audio_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"
                )
            
            result = {
                "text": transcript.text.strip(),
                "duration": None,  # Whisper doesn't return duration
                "confidence": None,  # Whisper doesn't provide confidence
                "model": "whisper-1"
            }
            
            print(f"✓ Transcribed: {result['text'][:60]}..." if len(result['text']) > 60 else f"✓ Transcribed: {result['text']}")
            
            return result
        
        except Exception as e:
            print(f"ERROR transcribing audio: {str(e)}")
            raise
    
    def transcribe_file(self, audio_path: str, output_path: str = None) -> str:
        """
        Transcribe audio and save result to JSON file.
        
        Args:
            audio_path: Path to audio file
            output_path: Where to save JSON result (default: same dir, .json extension)
        
        Returns:
            Transcribed text
        """
        if output_path is None:
            output_path = audio_path.replace('.wav', '.json').replace('.mp3', '.json')
        
        result = self.transcribe_audio(audio_path)
        
        # Save transcription result
        with open(output_path, 'w') as f:
            json.dump({
                "audio_file": audio_path,
                "timestamp": datetime.now().isoformat(),
                "transcription": result
            }, f, indent=2)
        
        print(f"✓ Saved transcription: {output_path}")
        
        return result['text']


def main():
    """CLI interface for audio recording and transcription."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Audio Recording & Speech-to-Text")
    
    subparsers = parser.add_subparsers(dest='action', help='Action to perform')
    
    # Record subcommand
    record_parser = subparsers.add_parser('record', help='Record audio from microphone')
    record_parser.add_argument('--duration', type=int, default=10, help='Recording duration (seconds)')
    record_parser.add_argument('--output', help='Output file path (default: data/sessions/audio_TIMESTAMP.wav)')
    
    # Transcribe subcommand
    transcribe_parser = subparsers.add_parser('transcribe', help='Transcribe audio file')
    transcribe_parser.add_argument('--audio', required=True, help='Path to audio file')
    transcribe_parser.add_argument('--output', help='Output JSON file (default: same dir, .json extension)')
    
    # Interactive session (record + transcribe)
    session_parser = subparsers.add_parser('session', help='Interactive record + transcribe session')
    session_parser.add_argument('--duration', type=int, default=10, help='Recording duration (seconds)')
    session_parser.add_argument('--session-id', help='Session ID (for organizing files)')
    
    args = parser.parse_args()
    
    if args.action == 'record':
        if not PYAUDIO_AVAILABLE:
            print("ERROR: pyaudio not installed. Run: pip install pyaudio")
            sys.exit(1)
        
        recorder = AudioRecorder()
        audio_path = recorder.record_audio(
            duration=args.duration,
            output_path=args.output
        )
        print(f"\nAudio saved to: {audio_path}")
    
    elif args.action == 'transcribe':
        if not OPENAI_AVAILABLE:
            print("ERROR: openai not installed. Run: pip install openai")
            sys.exit(1)
        
        try:
            stt = SpeechToText()
            text = stt.transcribe_file(
                audio_path=args.audio,
                output_path=args.output
            )
            print(f"\nTranscription:\n{text}")
        except Exception as e:
            print(f"ERROR: {str(e)}")
            sys.exit(1)
    
    elif args.action == 'session':
        if not PYAUDIO_AVAILABLE or not OPENAI_AVAILABLE:
            print("ERROR: pyaudio and openai required. Run: pip install pyaudio openai")
            sys.exit(1)
        
        try:
            session_id = args.session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = f"data/sessions/{session_id}"
            os.makedirs(session_dir, exist_ok=True)
            
            # Record
            recorder = AudioRecorder()
            audio_path = recorder.record_audio(
                duration=args.duration,
                output_path=f"{session_dir}/audio.wav"
            )
            
            # Transcribe
            stt = SpeechToText()
            text = stt.transcribe_file(
                audio_path=audio_path,
                output_path=f"{session_dir}/transcription.json"
            )
            
            print(f"\n✓ Session complete: {session_dir}")
            print(f"Transcription: {text}")
        
        except Exception as e:
            print(f"ERROR: {str(e)}")
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
