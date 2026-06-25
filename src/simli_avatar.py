"""Small Simli avatar client for examiner prompt playback.

The app remains responsible for assessment flow and grading. Simli is only used
as a presentation layer that turns already-selected examiner text into a short
talking-avatar video.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import requests


class SimliAvatarError(RuntimeError):
    """Raised when an avatar clip cannot be prepared."""


@dataclass(frozen=True)
class SimliAvatarConfig:
    simli_api_key: str
    face_id: str
    openai_api_key: str
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    audio_sample_rate: int = 24000


def avatar_enabled() -> bool:
    """Return True only when the demo toggle and required credentials are set."""
    enabled = os.getenv("ENABLE_SIMLI_AVATAR", "").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and bool(load_config())


def load_config() -> SimliAvatarConfig | None:
    simli_api_key = os.getenv("SIMLI_API_KEY", "").strip()
    face_id = os.getenv("SIMLI_FACE_ID", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not simli_api_key or not face_id or not openai_api_key:
        return None

    return SimliAvatarConfig(
        simli_api_key=simli_api_key,
        face_id=face_id,
        openai_api_key=openai_api_key,
        tts_model=os.getenv("SIMLI_TTS_MODEL", "tts-1").strip() or "tts-1",
        tts_voice=os.getenv("SIMLI_TTS_VOICE", "alloy").strip() or "alloy",
        audio_sample_rate=_int_env("SIMLI_AUDIO_SAMPLE_RATE", 24000),
    )


def create_avatar_video_url(text: str, *, config: SimliAvatarConfig | None = None) -> str:
    """Generate examiner speech audio, send it to Simli, and return a video URL."""
    clean_text = " ".join((text or "").split())
    if not clean_text:
        raise SimliAvatarError("No examiner text was provided for the avatar.")

    config = config or load_config()
    if not config:
        raise SimliAvatarError(
            "Simli avatar is not configured. Set SIMLI_API_KEY, SIMLI_FACE_ID, and OPENAI_API_KEY."
        )

    audio = _create_tts_audio(clean_text, config=config)
    payload = {
        "faceId": config.face_id,
        "audioBase64": base64.b64encode(audio).decode("ascii"),
        "audioFormat": "mp3",
        "audioSampleRate": config.audio_sample_rate,
        "audioChannelCount": 1,
        "videoStartingFrame": 0,
    }
    response = requests.post(
        "https://api.simli.ai/static/audio",
        headers={
            "x-simli-api-key": config.simli_api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    data = _response_data(response, "generate static avatar video")
    video_url = data.get("mp4_url") or data.get("hls_url")
    if not video_url:
        raise SimliAvatarError("Simli did not return an avatar video URL.")
    return str(video_url)


def _create_tts_audio(text: str, *, config: SimliAvatarConfig) -> bytes:
    try:
        from openai import OpenAI
    except Exception as error:
        raise SimliAvatarError("OpenAI package is unavailable for avatar speech generation.") from error

    client = OpenAI(api_key=config.openai_api_key)
    try:
        speech = client.audio.speech.create(
            model=config.tts_model,
            voice=config.tts_voice,
            input=text,
            response_format="mp3",
        )
    except Exception as error:
        raise SimliAvatarError(f"OpenAI TTS could not create examiner audio: {error}") from error

    if hasattr(speech, "read"):
        return speech.read()
    content = getattr(speech, "content", None)
    if isinstance(content, bytes):
        return content
    try:
        return bytes(speech)
    except TypeError as error:
        raise SimliAvatarError("OpenAI TTS returned an unsupported audio response.") from error


def _response_data(response: requests.Response, action: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise SimliAvatarError(f"Simli {action} returned non-JSON response.") from error

    if response.status_code >= 400:
        message = payload.get("message") or payload.get("detail") or payload.get("error") or response.text
        raise SimliAvatarError(f"Simli {action} failed ({response.status_code}): {message}")

    if not isinstance(payload, dict):
        raise SimliAvatarError(f"Simli {action} returned an unexpected response.")
    return payload


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
