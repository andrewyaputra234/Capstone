"""Browser-audio transcription and cautious delivery indicators for the oral portal.

The indicators are intentionally advisory: a general speech-to-text model does
not provide phoneme-level pronunciation scoring or a reliable emotional-tone
judgement. They help an examiner review pace and pitch variation alongside the
recording and transcript.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _safe_filename(name: str) -> str:
    suffix = Path(name).suffix.lower() or ".wav"
    return f"speech_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"


def analyse_delivery(audio_path: str | Path, transcript: str) -> dict[str, Any]:
    """Return non-diagnostic pace/pitch indicators from an uploaded recording."""
    result: dict[str, Any] = {
        "status": "unavailable",
        "disclaimer": (
            "Automated delivery indicators are for examiner review only. They are not a "
            "pronunciation, accent, emotion, or official oral-exam score."
        ),
    }
    try:
        import librosa
        import numpy as np

        audio, sample_rate = librosa.load(str(audio_path), sr=None, mono=True)
        duration = float(librosa.get_duration(y=audio, sr=sample_rate))
        words = len(re.findall(r"\b[\w']+\b", transcript))
        wpm = round(words / duration * 60, 1) if duration > 0 else None
        pitch = librosa.yin(audio, fmin=75, fmax=400, sr=sample_rate)
        voiced_pitch = pitch[np.isfinite(pitch) & (pitch > 0)]
        pitch_range = None
        if len(voiced_pitch) >= 3:
            low, high = np.percentile(voiced_pitch, [10, 90])
            pitch_range = round(float(12 * np.log2(high / low)), 1) if low > 0 else None

        notes = []
        if wpm is not None and wpm < 80:
            notes.append("Pace appears slow; check whether pauses support meaning or interrupt fluency.")
        elif wpm is not None and wpm > 180:
            notes.append("Pace appears fast; check whether words remain clear and well-paced.")
        elif wpm is not None:
            notes.append("Pace falls within a broad conversational range; listen to the recording for clarity.")
        if pitch_range is not None and pitch_range < 2:
            notes.append("Limited pitch variation was detected; listen for opportunities to use more expression.")
        elif pitch_range is not None:
            notes.append("Some pitch variation was detected; the examiner should judge whether it fits the meaning.")

        result.update(
            {
                "status": "available",
                "duration_seconds": round(duration, 1),
                "words_per_minute": wpm,
                "pitch_range_semitones": pitch_range,
                "notes": notes,
            }
        )
    except Exception as error:
        result["reason"] = str(error)
    return result


def transcribe_streamlit_audio(
    uploaded_audio,
    session_dir: str | Path = "data/sessions",
    *,
    include_delivery: bool = True,
) -> dict[str, Any]:
    """Persist a browser recording, transcribe it, and return reviewable metadata."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for speech-to-text.")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("The OpenAI Python package is required for speech-to-text.") from error

    target_dir = Path(session_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    audio_path = target_dir / _safe_filename(getattr(uploaded_audio, "name", "speech.wav"))
    audio_path.write_bytes(uploaded_audio.getbuffer())

    try:
        client = OpenAI(api_key=api_key)
        with audio_path.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
            )
        text = str(transcription.text).strip()
        if not text:
            raise ValueError("No speech was detected in this recording.")
        delivery = analyse_delivery(audio_path, text) if include_delivery else {
            "status": "skipped",
            "disclaimer": "Delivery indicators were skipped for faster image-question assessment.",
        }
        transcription_path = audio_path.with_suffix(".json")
        transcription_path.write_text(
            json.dumps(
                {
                    "audio_path": str(audio_path),
                    "transcript": text,
                    "delivery_indicators": delivery,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "text": text,
            "audio_path": str(audio_path),
            "transcription_path": str(transcription_path),
            "delivery_indicators": delivery,
            "mode": "voice",
        }
    except Exception:
        # Do not leave an orphaned recording when transcription fails.
        audio_path.unlink(missing_ok=True)
        raise
