"""Anam avatar client for live examiner prompt playback.

The app still owns the assessment logic. Anam is used as a presentation layer:
Streamlit creates a short-lived session token on the server, then the browser
opens a live avatar session and asks the persona to speak the selected prompt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


class AnamAvatarError(RuntimeError):
    """Raised when an Anam avatar session cannot be prepared."""


@dataclass(frozen=True)
class AnamAvatarConfig:
    api_key: str
    persona_id: str = ""
    avatar_id: str = ""
    voice_id: str = ""
    llm_id: str = ""
    avatar_model: str = "cara-4"
    system_prompt: str = (
        "You are a calm oral examiner. Speak the exact question text provided "
        "by the application and nothing else. Do not greet the student, "
        "introduce yourself, add opening small talk, add encouragement, or add "
        "closing remarks."
    )
    api_base_url: str = "https://api.anam.ai"


def avatar_enabled() -> bool:
    """Return True only when Anam credentials identify a usable persona."""
    return bool(load_config())


def load_config() -> AnamAvatarConfig | None:
    api_key = os.getenv("ANAM_API_KEY", "").strip()
    persona_id = os.getenv("ANAM_PERSONA_ID", "").strip()
    avatar_id = os.getenv("ANAM_AVATAR_ID", "").strip()
    voice_id = os.getenv("ANAM_VOICE_ID", "").strip()
    llm_id = os.getenv("ANAM_LLM_ID", "").strip()

    has_ephemeral_persona = bool(avatar_id and voice_id and llm_id)
    if not api_key or not (persona_id or has_ephemeral_persona):
        return None

    return AnamAvatarConfig(
        api_key=api_key,
        persona_id=persona_id,
        avatar_id=avatar_id,
        voice_id=voice_id,
        llm_id=llm_id,
        avatar_model=os.getenv("ANAM_AVATAR_MODEL", "cara-4").strip() or "cara-4",
        system_prompt=os.getenv(
            "ANAM_SYSTEM_PROMPT",
            AnamAvatarConfig.system_prompt,
        ).strip()
        or AnamAvatarConfig.system_prompt,
        api_base_url=os.getenv("ANAM_API_BASE_URL", "https://api.anam.ai").strip().rstrip("/")
        or "https://api.anam.ai",
    )


def create_session_token(*, config: AnamAvatarConfig | None = None) -> str:
    """Create a short-lived browser token for an Anam persona session."""
    config = config or load_config()
    if not config:
        raise AnamAvatarError(
            "Anam avatar is not configured. Set ANAM_API_KEY and ANAM_PERSONA_ID, "
            "or set ANAM_API_KEY with ANAM_AVATAR_ID, ANAM_VOICE_ID, and ANAM_LLM_ID."
        )

    persona_config: dict[str, Any]
    if config.persona_id:
        persona_config = {"personaId": config.persona_id}
    else:
        persona_config = {
            "name": "Capstone Oral Examiner",
            "avatarId": config.avatar_id,
            "avatarModel": config.avatar_model,
            "voiceId": config.voice_id,
            "llmId": config.llm_id,
            "systemPrompt": config.system_prompt,
        }

    payload: dict[str, Any] = {"personaConfig": persona_config}
    response = requests.post(
        f"{config.api_base_url}/v1/auth/session-token",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    data = _response_data(response, "create session token")
    token = data.get("sessionToken")
    if not token:
        raise AnamAvatarError("Anam did not return a session token.")
    return str(token)


def _response_data(response: requests.Response, action: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise AnamAvatarError(f"Anam {action} returned non-JSON response.") from error

    if response.status_code >= 400:
        message = payload.get("message") or payload.get("detail") or payload.get("error") or response.text
        raise AnamAvatarError(f"Anam {action} failed ({response.status_code}): {message}")

    if not isinstance(payload, dict):
        raise AnamAvatarError(f"Anam {action} returned an unexpected response.")
    return payload
