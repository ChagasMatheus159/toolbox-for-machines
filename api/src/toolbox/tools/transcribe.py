"""POST /v1/transcribe — Audio transcription via whisper.cpp."""

import base64
import logging
import tempfile
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from toolbox.config import settings

log = logging.getLogger("toolbox.transcribe")
router = APIRouter()


class TranscribeRequest(BaseModel):
    audio_url: Optional[str] = None
    audio_b64: Optional[str] = None
    mime_type: str = "audio/wav"
    language: str = "en"


class TranscribeResponse(BaseModel):
    transcript: str
    language: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(req: TranscribeRequest, request: Request):
    """Transcribe audio to text using whisper.cpp."""
    if not req.audio_url and not req.audio_b64:
        raise HTTPException(status_code=400, detail="Either audio_url or audio_b64 is required.")

    http = request.app.state.http

    # Get audio bytes
    if req.audio_url:
        try:
            r = await http.get(req.audio_url, timeout=30)
            r.raise_for_status()
            audio_bytes = r.content
        except Exception as e:
            log.error("Failed to download audio %s: %s", req.audio_url, e)
            raise HTTPException(status_code=502, detail=f"Failed to download audio: {e}")
    else:
        try:
            audio_bytes = base64.b64decode(req.audio_b64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {e}")

    # Send to whisper.cpp server
    try:
        # whisper.cpp server expects multipart form with file
        files = {"file": ("audio.wav", audio_bytes, req.mime_type)}
        data = {"language": req.language, "response_format": "json"}

        r = await http.post(
            f"{settings.whisper_url}/inference",
            files=files,
            data=data,
            timeout=120,  # Audio can take a while
        )
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        log.error("Whisper request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Whisper transcription error: {e}")

    # Parse response (whisper.cpp returns {"text": "..."})
    transcript = result.get("text", "").strip()

    return TranscribeResponse(transcript=transcript, language=req.language)
