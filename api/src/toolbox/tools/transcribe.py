"""POST /v1/transcribe — Audio transcription via whisper.cpp."""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from toolbox.config import settings
from toolbox.validation import validate_url

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

    if req.audio_url:
        await validate_url(req.audio_url)

    http = request.app.state.http

    MAX_AUDIO_BYTES = 100 * 1024 * 1024  # 100MB

    # Get audio bytes
    if req.audio_url:
        try:
            r = await http.get(req.audio_url, timeout=30)
            r.raise_for_status()
            cl_header = r.headers.get("content-length")
            if cl_header and int(cl_header) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=400, detail="Audio too large (max 100MB).")
            audio_bytes = r.content
            if len(audio_bytes) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=400, detail="Audio too large (max 100MB).")
        except HTTPException:
            raise
        except Exception as e:
            log.error("Failed to download audio %s: %s", req.audio_url, e)
            raise HTTPException(status_code=502, detail="Failed to download audio.")
    else:
        try:
            audio_bytes = base64.b64decode(req.audio_b64)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid base64 audio data.")

    # Send to whisper.cpp server
    try:
        files = {"file": ("audio.wav", audio_bytes, req.mime_type)}
        data = {"language": req.language, "response_format": "json"}

        r = await http.post(
            f"{settings.whisper_url}/inference",
            files=files,
            data=data,
            timeout=120,
        )
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        log.error("Whisper request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Whisper transcription error: {e}")

    transcript = result.get("text", "").strip()

    return TranscribeResponse(transcript=transcript, language=req.language)


@router.post("/audio/transcriptions")
async def transcribe_openai(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("en"),
    model: Optional[str] = Form(None),
):
    """OpenAI-compatible audio transcription endpoint."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="file field is required.")

    mime_type = file.content_type or "audio/wav"

    try:
        files = {"file": (file.filename or "audio.wav", audio_bytes, mime_type)}
        data = {"language": language, "response_format": "json"}

        r = await request.app.state.http.post(
            f"{settings.whisper_url}/inference",
            files=files,
            data=data,
            timeout=120,
        )
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        log.error("Whisper request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Whisper transcription error: {e}")

    return {"text": result.get("text", "").strip()}
