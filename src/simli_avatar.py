"""Small Simli avatar client for examiner prompt playback.

The app remains responsible for assessment flow and grading. Simli is only used
as a presentation layer that turns already-selected examiner text into a short
talking-avatar video.
"""

from __future__ import annotations

import base64
import os
import time
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
    mp4_wait_seconds: float = 35.0
    poll_interval_seconds: float = 1.5
    prefer_hls: bool = True


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
        mp4_wait_seconds=max(0.0, _float_env("SIMLI_MP4_WAIT_SECONDS", 35.0)),
        poll_interval_seconds=max(0.5, _float_env("SIMLI_POLL_INTERVAL_SECONDS", 1.5)),
        prefer_hls=_bool_env("SIMLI_PREFER_HLS", True),
    )


def create_avatar_video_url(text: str, *, config: SimliAvatarConfig | None = None) -> str:
    """Generate examiner speech audio, send it to Simli, and return a playable video URL."""
    asset = create_avatar_video_asset(text, config=config, allow_unready=False)
    url = asset.get("url")
    if not url:
        raise SimliAvatarError("Simli did not return an avatar video URL.")
    return str(url)


def create_avatar_video_asset(
    text: str,
    *,
    config: SimliAvatarConfig | None = None,
    allow_unready: bool = True,
) -> dict[str, Any]:
    """Generate an avatar and return the best video asset information available.

    Simli can return video URLs before the files are actually playable. When
    allow_unready is true, keep those URLs so the app can retry/preview later
    instead of throwing the whole avatar preparation away.
    """
    clean_text = " ".join((text or "").split())
    if not clean_text:
        raise SimliAvatarError("No examiner text was provided for the avatar.")

    config = config or load_config()
    if not config:
        raise SimliAvatarError(
            "Simli avatar is not configured. Set SIMLI_API_KEY, SIMLI_FACE_ID, and OPENAI_API_KEY."
        )

    _log(f"creating TTS audio ({len(clean_text)} chars)")
    audio = _create_tts_audio(clean_text, config=config)
    _log(f"TTS audio ready ({len(audio) / 1024:.1f} KB); sending to Simli")
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
    _log("Simli response received; selecting playable video")
    _log(f"Simli response URL fields: mp4_url={bool(data.get('mp4_url'))}, hls_url={bool(data.get('hls_url'))}")
    video_url = _select_playable_video_url(data, config=config)
    if video_url:
        _log("avatar video URL ready")
        return {
            "url": str(video_url),
            "ready": True,
            "kind": "hls" if ".m3u8" in str(video_url).lower() else "mp4",
            "mp4_url": data.get("mp4_url"),
            "hls_url": data.get("hls_url"),
        }
    if allow_unready:
        fallback_url = data.get("hls_url") or data.get("mp4_url")
        if fallback_url:
            _log("avatar URL returned by Simli but not playable yet; saving as pending")
            return {
                "url": str(fallback_url),
                "ready": False,
                "kind": "hls_pending" if ".m3u8" in str(fallback_url).lower() else "mp4_pending",
                "mp4_url": data.get("mp4_url"),
                "hls_url": data.get("hls_url"),
            }
    raise SimliAvatarError("Simli did not return an avatar video URL.")


def _select_playable_video_url(data: dict[str, Any], *, config: SimliAvatarConfig) -> str | None:
    """Prefer MP4 for Streamlit playback, but fall back to HLS while MP4 is cooking."""
    mp4_url = data.get("mp4_url")
    hls_url = data.get("hls_url")
    if config.prefer_hls and hls_url:
        _log("checking HLS stream availability first")
        if _wait_until_url_available(str(hls_url), timeout_seconds=6.0, poll_interval=config.poll_interval_seconds):
            _log("HLS stream is available")
            return str(hls_url)
        _log("HLS stream was not available yet; checking MP4")
    if mp4_url:
        eta = _extract_mp4_eta(data)
        wait_seconds = max(config.mp4_wait_seconds, min(60.0, eta + 8.0 if eta else 0.0))
        _log(f"MP4 URL returned; waiting up to {wait_seconds:.1f}s for browser-ready file")
        if _wait_until_url_available(str(mp4_url), timeout_seconds=wait_seconds, poll_interval=config.poll_interval_seconds):
            _log("MP4 is available")
            return str(mp4_url)
        _log("MP4 not ready before timeout; falling back if HLS is available")
    if hls_url and not config.prefer_hls:
        _log("checking HLS stream availability")
        if _wait_until_url_available(str(hls_url), timeout_seconds=8.0, poll_interval=config.poll_interval_seconds):
            _log("HLS stream is available")
            return str(hls_url)
        _log("HLS stream was not available")
    return None


def _extract_mp4_eta(data: dict[str, Any]) -> float:
    """Simli currently exposes this with a misspelled key in some responses."""
    for key in ("mp4_availability_eta_seconds", "mp4_availablility_eta_seconds"):
        value = data.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _wait_until_url_available(url: str, *, timeout_seconds: float, poll_interval: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    while time.monotonic() <= deadline:
        attempt += 1
        try:
            with requests.get(url, timeout=10, stream=True) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                try:
                    preview = next(response.iter_content(chunk_size=128), b"").strip()
                except StopIteration:
                    preview = b""
                ok = (
                    response.status_code == 200
                    and "json" not in content_type
                    and not preview.lstrip().startswith(b"{")
                    and preview
                )
            if ok:
                return True
        except requests.RequestException:
            pass
        _log(f"video URL not ready yet; poll {attempt}")
        time.sleep(poll_interval)
    return False


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


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _log(message: str) -> None:
    enabled = os.getenv("AVATAR_PRELOAD_TERMINAL_LOG", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [simli-avatar] {message}", flush=True)
