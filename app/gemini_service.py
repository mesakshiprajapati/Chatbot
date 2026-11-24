"""
Gemini Service Module for Study Buddy Chat.
Handles client configuration, multimodal payload construction,
and error handling using the official google-genai SDK.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Resolve root .env path reliably relative to the project root (parent of app/)
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


def load_root_env() -> None:
    """Load or reload environment variables from the project root .env file."""
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)
    else:
        load_dotenv(override=True)


# Load environment on module import
load_root_env()

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

# Default model supporting text, image, and audio multimodal inputs
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
SYSTEM_INSTRUCTION = (
    "You are Study Buddy, an encouraging, highly knowledgeable, and structured AI tutor. "
    "Your mission is to help students learn and retain knowledge effectively. "
    "Guidelines:\n"
    "1. Explain concepts step-by-step using clear headings, bullet points, and intuitive analogies.\n"
    "2. For images (such as diagrams, math equations, textbook pages, or charts), provide a clear, "
    "thorough explanation of the visual components and their educational significance.\n"
    "3. For audio (such as lectures or study notes), provide an accurate transcription or structured "
    "summary highlighting key concepts, definitions, and study takeaways.\n"
    "4. Always maintain a warm, supportive, and academically rigorous tone."
)

DEFAULT_IMAGE_PROMPT = (
    "Please analyze this study material or diagram. Explain its core concepts, key labels or formulas, "
    "and provide a structured breakdown to help me understand it thoroughly."
)

DEFAULT_AUDIO_PROMPT = (
    "Please transcribe and provide a clear, structured summary of this study audio recording. "
    "Highlight key concepts, main topics discussed, and essential takeaways for studying."
)


class GeminiServiceError(Exception):
    """Base exception for Gemini service issues."""
    def __init__(self, message: str, error_type: str = "provider_error"):
        super().__init__(message)
        self.message = message
        self.error_type = error_type


class GeminiAuthError(GeminiServiceError):
    """Raised when GEMINI_API_KEY is missing or invalid."""
    def __init__(self, message: str = "Gemini API key is missing or invalid."):
        super().__init__(message, error_type="auth_error")


class GeminiQuotaError(GeminiServiceError):
    """Raised when API rate limits or quotas are exceeded."""
    def __init__(self, message: str = "Gemini API quota exceeded or rate limit reached."):
        super().__init__(message, error_type="quota_error")


class GeminiTimeoutError(GeminiServiceError):
    """Raised when an API call times out."""
    def __init__(self, message: str = "Gemini API request timed out."):
        super().__init__(message, error_type="timeout_error")


class GeminiValidationError(GeminiServiceError):
    """Raised when request payload or media format is invalid."""
    def __init__(self, message: str = "Invalid input or unsupported media format."):
        super().__init__(message, error_type="validation_error")


def get_api_key() -> Optional[str]:
    """Retrieve the Gemini API key from environment variables."""
    load_root_env()
    key = os.getenv("GEMINI_API_KEY")
    if key:
        key = key.strip()
    return key if key else None


def is_api_key_configured() -> bool:
    """Check if a non-placeholder API key is configured."""
    key = get_api_key()
    if not key:
        return False
    # Check for placeholder values
    placeholders = {
        "your_gemini_api_key_here",
        "your_api_key_here",
        "insert_key_here",
        "api_key",
        "changeme"
    }
    return key.lower() not in placeholders


def get_configured_model() -> str:
    """Return the configured Gemini model name."""
    load_root_env()
    model = os.getenv("GEMINI_MODEL")
    if model:
        model = model.strip()
    return model if model else DEFAULT_GEMINI_MODEL


def get_gemini_client() -> genai.Client:
    """Create and return an authenticated genai.Client instance."""
    api_key = get_api_key()
    if not api_key or not is_api_key_configured():
        raise GeminiAuthError(
            "Gemini API key is not configured. Please add your GEMINI_API_KEY to the .env file. "
            "You can obtain a free API key at https://aistudio.google.com/."
        )
    return genai.Client(api_key=api_key)


async def generate_multimodal_response(
    message: Optional[str] = None,
    media_bytes: Optional[bytes] = None,
    media_mime_type: Optional[str] = None,
    modality: str = "text",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    timeout_seconds: float = 45.0,
) -> Dict[str, Any]:
    """
    Generate an AI response using the official google-genai SDK.
    Supports text, image, and audio inputs with multi-turn conversation history.
    """
    client = get_gemini_client()
    model_name = get_configured_model()

    # Determine prompt text
    cleaned_message = (message or "").strip()
    if not cleaned_message:
        if modality == "image":
            prompt_text = DEFAULT_IMAGE_PROMPT
        elif modality == "audio":
            prompt_text = DEFAULT_AUDIO_PROMPT
        else:
            raise GeminiValidationError("Message cannot be empty when no media file is attached.")
    else:
        prompt_text = cleaned_message

    # Build contents array
    contents: List[types.Content] = []

    # Add conversation history (up to last 10 turns to maintain context)
    if conversation_history:
        # Keep recent turns to prevent excessive context size
        recent_history = conversation_history[-10:]
        for turn in recent_history:
            role = turn.get("role", "user")
            # Map "assistant" to Gemini's "model" role
            gemini_role = "model" if role in ("assistant", "model") else "user"
            turn_text = (turn.get("text") or turn.get("content") or "").strip()
            if turn_text:
                contents.append(
                    types.Content(
                        role=gemini_role,
                        parts=[types.Part.from_text(text=turn_text)]
                    )
                )

    # Build current turn parts
    current_parts: List[types.Part] = []

    # If media is provided, construct Part.from_bytes
    if media_bytes and media_mime_type:
        try:
            media_part = types.Part.from_bytes(
                data=media_bytes,
                mime_type=media_mime_type
            )
            current_parts.append(media_part)
        except Exception as e:
            logger.error(f"Failed to create media Part: {e}")
            raise GeminiValidationError(f"Could not process media attachment: {str(e)}")

    # Add the text prompt part
    current_parts.append(types.Part.from_text(text=prompt_text))

    # Append current turn to contents
    contents.append(types.Content(role="user", parts=current_parts))

    # Configure generation
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.7,
        max_output_tokens=2048,
    )

    try:
        # Execute asynchronous content generation with timeout
        logger.info(f"Dispatching Gemini request: model={model_name}, modality={modality}")
        
        # client.aio.models.generate_content is native async
        generate_coro = client.aio.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        response = await asyncio.wait_for(generate_coro, timeout=timeout_seconds)

        # Extract reply text
        reply_text = response.text if response and response.text else None

        if not reply_text:
            # Check if there are parts or candidates
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    reply_text = "".join(
                        part.text for part in candidate.content.parts if hasattr(part, "text") and part.text
                    )
                # Check finish reason
                if candidate.finish_reason and str(candidate.finish_reason) != "STOP":
                    logger.warning(f"Gemini finish reason: {candidate.finish_reason}")
            
            if not reply_text:
                raise GeminiServiceError(
                    "The model did not generate a text response. This may occur if content safety filters were triggered.",
                    error_type="provider_error"
                )

        return {
            "reply": reply_text.strip(),
            "model": model_name,
            "modality": modality,
        }

    except asyncio.TimeoutError:
        logger.error(f"Gemini request timed out after {timeout_seconds}s")
        raise GeminiTimeoutError(
            f"The AI service took longer than {int(timeout_seconds)} seconds to respond. Please try again."
        )

    except genai_errors.APIError as api_err:
        logger.error(f"Gemini API Error: {api_err}")
        err_msg = str(api_err)
        status_code = getattr(api_err, "code", None)

        if status_code in (401, 403) or "API_KEY_INVALID" in err_msg or "PERMISSION_DENIED" in err_msg:
            raise GeminiAuthError(
                "Invalid Gemini API key or access denied. Please verify your GEMINI_API_KEY in the .env file."
            )
        elif status_code == 429 or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
            raise GeminiQuotaError(
                "Gemini API rate limit or free tier quota has been reached. Please wait a minute and try again."
            )
        elif status_code in (500, 502, 503, 504) or "UNAVAILABLE" in err_msg:
            raise GeminiServiceError(
                "Google Gemini service is momentarily unavailable. Please retry in a few moments.",
                error_type="provider_error"
            )
        else:
            raise GeminiServiceError(
                f"Gemini API returned an error: {err_msg}",
                error_type="provider_error"
            )

    except (GeminiAuthError, GeminiQuotaError, GeminiTimeoutError, GeminiValidationError):
        raise

    except Exception as exc:
        logger.exception("Unexpected error in Gemini service")
        err_str = str(exc)
        if "API_KEY" in err_str or "api key" in err_str.lower():
            raise GeminiAuthError(
                "Gemini API key error. Please check your GEMINI_API_KEY in the .env file."
            )
        raise GeminiServiceError(
            f"An error occurred while communicating with Gemini: {err_str}",
            error_type="provider_error"
        )
