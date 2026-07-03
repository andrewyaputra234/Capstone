import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anam_avatar import avatar_enabled, load_config


class AnamAvatarConfigTest(unittest.TestCase):
    def test_avatar_disabled_without_required_credentials(self):
        with patch.dict(os.environ, {"ENABLE_ANAM_AVATAR": "true"}, clear=True):
            self.assertIsNone(load_config())
            self.assertFalse(avatar_enabled())

    def test_avatar_enabled_with_saved_persona(self):
        env = {
            "ANAM_API_KEY": "test-key",
            "ANAM_PERSONA_ID": "persona-id",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            self.assertIsNotNone(config)
            self.assertTrue(avatar_enabled())
            self.assertEqual(config.api_key, "test-key")
            self.assertEqual(config.persona_id, "persona-id")

    def test_avatar_enabled_with_runtime_persona_parts(self):
        env = {
            "ANAM_API_KEY": "test-key",
            "ANAM_AVATAR_ID": "avatar-id",
            "ANAM_VOICE_ID": "voice-id",
            "ANAM_LLM_ID": "llm-id",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            self.assertIsNotNone(config)
            self.assertTrue(avatar_enabled())
            self.assertEqual(config.avatar_id, "avatar-id")
            self.assertEqual(config.voice_id, "voice-id")
            self.assertEqual(config.llm_id, "llm-id")


if __name__ == "__main__":
    unittest.main()
