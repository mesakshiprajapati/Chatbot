"""
FastAPI application for Study Buddy Chat.
Provides the multimodal chat API, strict media validation,
static file serving, and health checks.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.gemini_service import (
    generate_multimodal_response,
    is_api_key_configured,
    get_configured_model,
    GeminiServiceError,
    GeminiAuthError,
    GeminiQuotaError,
    GeminiTimeoutError,
    GeminiValidationError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("study_buddy")

app = FastAPI(
    title="Study Buddy Chat API",
    description="Multimodal AI Study Companion powered by Google Gemini",
    version="1.0.0"
)

# Enable CORS for local development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File size limits (in bytes)
MAX_IMAGE_SIZE = 5 * 1024 * 1024      # 5 MB
MAX_AUDIO_SIZE = 15 * 1024 * 1024     # 15 MB

# Status 413 constant compatibility
HTTP_413 = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)

# Supported formats and MIME types
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_MIME_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
}

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm"}
AUDIO_MIME_TYPES = {
    "audio/mpeg": [".mp3"],
    "audio/mp3": [".mp3"],
    "audio/wav": [".wav"],
    "audio/x-wav": [".wav"],
    "audio/wave": [".wav"],
    "audio/m4a": [".m4a"],
    "audio/x-m4a": [".m4a"],
    "audio/mp4": [".m4a"],
    "audio/aac": [".aac"],
    "audio/x-aac": [".aac"],
    "audio/ogg": [".ogg"],
    "application/ogg": [".ogg"],
    "audio/flac": [".flac"],
    "audio/x-flac": [".flac"],
    "audio/webm": [".webm"],
}


def validate_image_magic_bytes(header: bytes) -> bool:
    """Validate image magic bytes to verify actual file content matches format."""
    if len(header) < 12:
        return False
    # JPEG: starts with FF D8 FF
    if header.startswith(b"\xff\xd8\xff"):
        return True
    # PNG: starts with 89 50 4E 47 0D 0A 1A 0A
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    # WebP: starts with RIFF and has WEBP at offset 8
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return True
    return False


def validate_audio_magic_bytes(header: bytes) -> bool:
    """Validate audio file magic bytes / signatures."""
    if len(header) < 4:
        return False
    # MP3 ID3v2 tag
    if header.startswith(b"ID3"):
        return True
    # MP3 sync word (MPEG audio frame header: 0xFF followed by 0xFB, 0xF3, 0xF2, 0xFA, 0xE0-0xFF)
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return True
    # WAV: RIFF....WAVE
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return True
    # Ogg container
    if header.startswith(b"OggS"):
        return True
    # FLAC signature
    if header.startswith(b"fLaC"):
        return True
    # M4A / MP4 container: 'ftyp' typically at offset 4
    if len(header) >= 8 and (header[4:8] == b"ftyp" or b"ftyp" in header[:16]):
        return True
    # WebM / Matroska: EBML header \x1a\x45\xdf\xa3
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return True
    # AAC ADTS syncword (0xFFF)
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xF0) == 0xF0:
        return True
    return False


def validate_uploaded_file(file: UploadFile, content: bytes) -> tuple[str, str]:
    """
    Validate uploaded media file for size, extension, MIME type, and magic bytes.
    Returns: (modality, validated_mime_type)
    Raises: HTTPException on invalid file.
    """
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Uploaded file must have a valid filename.", "error_type": "validation_error"}
        )

    ext = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "The uploaded file is empty (0 bytes).", "error_type": "validation_error"}
        )

    # Check for Image
    if ext in IMAGE_EXTENSIONS:
        if file_size > MAX_IMAGE_SIZE:
            size_mb = file_size / (1024 * 1024)
            raise HTTPException(
                status_code=HTTP_413,
                detail={
                    "error": f"Image file is too large ({size_mb:.1f} MB). Maximum allowed size is 5 MB.",
                    "error_type": "validation_error"
                }
            )

        # Validate magic bytes
        if not validate_image_magic_bytes(content[:32]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "The image file appears corrupted or invalid (signature check failed).",
                    "error_type": "validation_error"
                }
            )

        # Normalize MIME type
        if ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".png":
            mime = "image/png"
        elif ext == ".webp":
            mime = "image/webp"
        else:
            mime = content_type if content_type in IMAGE_MIME_TYPES else "image/jpeg"

        return "image", mime

    # Check for Audio
    elif ext in AUDIO_EXTENSIONS:
        if file_size > MAX_AUDIO_SIZE:
            size_mb = file_size / (1024 * 1024)
            raise HTTPException(
                status_code=HTTP_413,
                detail={
                    "error": f"Audio file is too large ({size_mb:.1f} MB). Maximum allowed size is 15 MB.",
                    "error_type": "validation_error"
                }
            )

        # Validate magic bytes
        if not validate_audio_magic_bytes(content[:32]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "The audio file appears corrupted or invalid (signature check failed).",
                    "error_type": "validation_error"
                }
            )

        # Normalize MIME type
        mime_map = {
            ".mp3": "audio/mp3",
            ".wav": "audio/wav",
            ".m4a": "audio/m4a",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".webm": "audio/webm",
        }
        mime = mime_map.get(ext, content_type or "audio/mp3")
        return "audio", mime

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": f"Unsupported file format '{ext}'. Allowed image formats: JPG, PNG, WebP. Allowed audio formats: MP3, WAV, M4A, AAC, OGG, FLAC, WebM.",
                "error_type": "validation_error"
            }
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint providing server status and configuration info."""
    api_configured = is_api_key_configured()
    model_name = get_configured_model()
    return JSONResponse(
        content={
            "status": "ok",
            "api_key_configured": api_configured,
            "model": model_name,
            "max_image_size_mb": 5,
            "max_audio_size_mb": 15,
            "supported_images": ["jpg", "jpeg", "png", "webp"],
            "supported_audio": ["mp3", "wav", "m4a", "aac", "ogg", "flac", "webm"],
        }
    )


@app.post("/api/chat")
async def chat_endpoint(
    message: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    conversation_history: Optional[str] = Form(None),
):
    """
    Multimodal chat endpoint supporting text, image, and audio inputs.
    """
    cleaned_message = (message or "").strip()
    media_bytes = None
    media_mime_type = None
    modality = "text"

    # Validate file if attached
    if file and file.filename:
        try:
            media_bytes = await file.read()
        except Exception as e:
            logger.error(f"Failed to read uploaded file: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Failed to read uploaded file.", "error_type": "validation_error"}
            )
        
        # Strictly validate size, extension, and magic bytes
        modality, media_mime_type = validate_uploaded_file(file, media_bytes)

    # If no file is attached, message is required
    if not media_bytes and not cleaned_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Please enter a message or attach a valid image or audio file.",
                "error_type": "validation_error"
            }
        )

    # Parse conversation history
    history_list = []
    if conversation_history:
        try:
            parsed = json.loads(conversation_history)
            if isinstance(parsed, list):
                history_list = parsed
        except Exception as json_err:
            logger.warning(f"Failed to parse conversation_history JSON: {json_err}")
            # Non-fatal: proceed with empty history rather than blocking user

    # Call Gemini Service
    try:
        result = await generate_multimodal_response(
            message=cleaned_message,
            media_bytes=media_bytes,
            media_mime_type=media_mime_type,
            modality=modality,
            conversation_history=history_list,
        )

        return JSONResponse(
            content={
                "success": True,
                "reply": result["reply"],
                "model": result["model"],
                "modality": result["modality"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    except GeminiAuthError as err:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": err.message, "error_type": err.error_type}
        )
    except GeminiQuotaError as err:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"success": False, "error": err.message, "error_type": err.error_type}
        )
    except GeminiTimeoutError as err:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"success": False, "error": err.message, "error_type": err.error_type}
        )
    except GeminiValidationError as err:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": err.message, "error_type": err.error_type}
        )
    except GeminiServiceError as err:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"success": False, "error": err.message, "error_type": err.error_type}
        )
    except Exception as exc:
        logger.exception("Unhandled error processing chat request")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": f"An unexpected server error occurred: {str(exc)}",
                "error_type": "server_error"
            }
        )


# Static directory setup
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serve the single-page application frontend."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(
        content={"message": "Study Buddy Chat API is running. index.html not yet installed."}
    )
