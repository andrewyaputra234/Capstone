import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from simli_avatar import avatar_enabled, load_config


class SimliAvatarConfigTest(unittest.TestCase):
    def test_avatar_disabled_without_required_credentials(self):
        with patch.dict(os.environ, {"ENABLE_SIMLI_AVATAR": "true"}, clear=True):
            self.assertIsNone(load_config())
            self.assertFalse(avatar_enabled())

    def test_avatar_enabled_with_toggle_and_credentials(self):
        env = {
            "ENABLE_SIMLI_AVATAR": "true",
            "SIMLI_API_KEY": "test-key",
            "SIMLI_FACE_ID": "face-id",
            "OPENAI_API_KEY": "openai-key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            self.assertIsNotNone(config)
            self.assertTrue(avatar_enabled())
            self.assertEqual(config.face_id, "face-id")
            self.assertEqual(config.tts_model, "tts-1")
            self.assertEqual(config.tts_voice, "alloy")


if __name__ == "__main__":
    unittest.main()
