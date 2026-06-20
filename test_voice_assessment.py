"""Local tests for audio-delivery indicators; transcription itself is provider-backed."""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from voice_assessment import analyse_delivery


class VoiceAssessmentTests(unittest.TestCase):
    def test_delivery_indicators_for_a_wav_recording(self) -> None:
        sample_rate = 16000
        duration_seconds = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "speech.wav"
            samples = [
                int(12000 * math.sin(2 * math.pi * 220 * index / sample_rate))
                for index in range(sample_rate * duration_seconds)
            ]
            with wave.open(str(path), "wb") as recording:
                recording.setnchannels(1)
                recording.setsampwidth(2)
                recording.setframerate(sample_rate)
                recording.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))

            indicators = analyse_delivery(path, "This is a short spoken response")

        self.assertEqual(indicators["status"], "available")
        self.assertGreater(indicators["duration_seconds"], 0)
        self.assertIsNotNone(indicators["words_per_minute"])
        self.assertIn("disclaimer", indicators)


if __name__ == "__main__":
    unittest.main()
