"""POST /v1/transcribe — Audio transcription via whisper.cpp."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel

from toolbox.config import settings
from toolbox.http_client import get_http_client
from toolbox.services import transcribe as transcribe_service, ToolboxError

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
async def transcribe(req: TranscribeRequest):
    """Transcribe audio to text using whisper.cpp."""
    try:
        return await transcribe_service(
            audio_url=req.audio_url,
            audio_b64=req.audio_b64,
            mime_type=req.mime_type,
            language=req.language,
        )
    except ToolboxError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


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
    http = get_http_client()

    try:
        files = {"file": (file.filename or "audio.wav", audio_bytes, mime_type)}
        data = {"language": language, "response_format": "json"}
        r = await http.post(
            f"{settings.whisper_url}/inference",
            files=files,
            data=data,
            timeout=120,
        )
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Whisper transcription error: {e}")

    return {"text": result.get("text", "").strip()}
