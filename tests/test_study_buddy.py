"""
Unit and integration test suite for Study Buddy Chat.
Tests health checks, media validation, error responses, and mock Gemini multimodal workflows.
"""

import io
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
import app.gemini_service as gemini_service
from app.gemini_service import (
    GeminiAuthError,
    GeminiQuotaError,
    GeminiTimeoutError,
    GeminiServiceError,
)

client = TestClient(app)

# Helper valid media bytes
VALID_PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
VALID_JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
VALID_WAV_HEADER = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
VALID_MP3_HEADER = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf58.29.100"


def test_serve_index():
    """Verify the root route serves the frontend HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Study Buddy Chat" in response.text
    assert "imageInput" in response.text
    assert "audioInput" in response.text


def test_health_check():
    """Verify health endpoint structure and defaults."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "api_key_configured" in data
    assert data["model"] == "gemini-3.8-flash"
    assert data["max_image_size_mb"] == 5
    assert data["max_audio_size_mb"] == 15


def test_empty_message_rejection():
    """Verify submitting empty or whitespace message without attachment is rejected."""
    # Completely empty
    resp1 = client.post("/api/chat", data={"message": ""})
    assert resp1.status_code == 400
    assert resp1.json()["detail"]["error_type"] == "validation_error"

    # Whitespace only
    resp2 = client.post("/api/chat", data={"message": "    \n\t  "})
    assert resp2.status_code == 400
    assert resp2.json()["detail"]["error_type"] == "validation_error"


def test_unsupported_file_extension():
    """Verify unsupported file extensions are rejected."""
    fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    response = client.post(
        "/api/chat",
        data={"message": "Analyze this file"},
        files={"file": ("malicious.exe", fake_exe, "application/x-msdownload")}
    )
    assert response.status_code == 400
    data = response.json()
    assert "Unsupported file format" in data["detail"]["error"]


def test_corrupted_image_magic_bytes():
    """Verify images with invalid magic bytes (e.g. text file renamed to .png) are rejected."""
    fake_png = io.BytesIO(b"This is just plain text, not a PNG image!")
    response = client.post(
        "/api/chat",
        data={"message": "Check this diagram"},
        files={"file": ("diagram.png", fake_png, "image/png")}
    )
    assert response.status_code == 400
    data = response.json()
    assert "corrupted or invalid" in data["detail"]["error"]


def test_oversized_image_rejection():
    """Verify images larger than 5MB are rejected with 413."""
    # 5MB + 1KB
    large_payload = VALID_PNG_HEADER + (b"\x00" * (5 * 1024 * 1024 + 1024))
    large_file = io.BytesIO(large_payload)
    response = client.post(
        "/api/chat",
        data={"message": "Big image"},
        files={"file": ("large.png", large_file, "image/png")}
    )
    assert response.status_code == 413
    data = response.json()
    assert "too large" in data["detail"]["error"]


def test_corrupted_audio_magic_bytes():
    """Verify audio with invalid magic bytes is rejected."""
    fake_audio = io.BytesIO(b"Corrupted audio stream bytes here")
    response = client.post(
        "/api/chat",
        data={"message": "Transcribe this"},
        files={"file": ("lecture.mp3", fake_audio, "audio/mpeg")}
    )
    assert response.status_code == 400
    data = response.json()
    assert "corrupted or invalid" in data["detail"]["error"]


def test_oversized_audio_rejection():
    """Verify audio larger than 15MB are rejected with 413."""
    # 15MB + 1KB
    large_payload = VALID_WAV_HEADER + (b"\x00" * (15 * 1024 * 1024 + 1024))
    large_file = io.BytesIO(large_payload)
    response = client.post(
        "/api/chat",
        data={"message": "Big lecture"},
        files={"file": ("lecture.wav", large_file, "audio/wav")}
    )
    assert response.status_code == 413
    data = response.json()
    assert "too large" in data["detail"]["error"]


def test_missing_api_key_returns_401():
    """Verify clean 401 response when API key is not configured."""
    with patch("app.gemini_service.is_api_key_configured", return_value=False):
        response = client.post(
            "/api/chat",
            data={"message": "Explain photosynthesis"}
        )
        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "auth_error"
        assert "GEMINI_API_KEY" in data["error"]


def test_text_chat_success():
    """Verify successful text prompt submission with mocked Gemini response."""
    mock_result = {
        "reply": "Photosynthesis is the process by which green plants convert light energy into chemical energy.",
        "model": "gemini-3.8-flash",
        "modality": "text",
    }
    with patch("app.main.generate_multimodal_response", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_result

        response = client.post(
            "/api/chat",
            data={
                "message": "Explain photosynthesis in one sentence.",
                "conversation_history": json.dumps([{"role": "user", "text": "Hi"}])
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["modality"] == "text"
        assert data["model"] == "gemini-3.8-flash"
        assert "Photosynthesis" in data["reply"]


def test_image_chat_success():
    """Verify successful image upload with question."""
    mock_result = {
        "reply": "The image shows a right-angled triangle illustrating the Pythagorean theorem: a^2 + b^2 = c^2.",
        "model": "gemini-3.8-flash",
        "modality": "image",
    }
    with patch("app.main.generate_multimodal_response", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_result

        img_file = io.BytesIO(VALID_PNG_HEADER + b"\x00" * 100)
        response = client.post(
            "/api/chat",
            data={"message": "What formula is shown here?"},
            files={"file": ("triangle.png", img_file, "image/png")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["modality"] == "image"
        assert "Pythagorean" in data["reply"]


def test_image_optional_message():
    """Verify image upload without text uses default study prompt and succeeds."""
    mock_result = {
        "reply": "This diagram illustrates the human circulatory system with arterial and venous flow.",
        "model": "gemini-3.8-flash",
        "modality": "image",
    }
    with patch("app.main.generate_multimodal_response", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_result

        img_file = io.BytesIO(VALID_JPEG_HEADER + b"\x00" * 100)
        response = client.post(
            "/api/chat",
            files={"file": ("heart.jpg", img_file, "image/jpeg")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["modality"] == "image"


def test_audio_chat_success():
    """Verify audio upload with transcription/summary response."""
    mock_result = {
        "reply": "Summary: The lecture explains Newton's three laws of motion with real-world examples.",
        "model": "gemini-3.8-flash",
        "modality": "audio",
    }
    with patch("app.main.generate_multimodal_response", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_result

        audio_file = io.BytesIO(VALID_WAV_HEADER + b"\x00" * 200)
        response = client.post(
            "/api/chat",
            data={"message": "Please summarize this lecture"},
            files={"file": ("physics.wav", audio_file, "audio/wav")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["modality"] == "audio"
        assert "Newton" in data["reply"]
        data = response.json()
        assert data["success"] is True
        assert data["modality"] == "audio"
        assert "Newton" in data["reply"]


def test_quota_error_handling():
    """Verify quota exceeded errors return 429 status code."""
    with patch("app.main.generate_multimodal_response", new_callable=AsyncMock) as mock_gen:
        mock_gen.side_effect = GeminiQuotaError("Rate limit reached. Please wait.")

        response = client.post("/api/chat", data={"message": "Hello"})
        assert response.status_code == 429
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "quota_error"


def test_timeout_error_handling():
    """Verify timeout errors return 504 status code."""
    with patch("app.main.generate_multimodal_response", new_callable=AsyncMock) as mock_gen:
        mock_gen.side_effect = GeminiTimeoutError("Request timed out after 45s.")

        response = client.post("/api/chat", data={"message": "Complex math question"})
        assert response.status_code == 504
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "timeout_error"


def test_default_model_is_gemini_3_8_flash():
    """Verify that when GEMINI_MODEL is missing, the default is gemini-3.8-flash."""
    with patch.dict("os.environ", {}, clear=False):
        import os
        if "GEMINI_MODEL" in os.environ:
            del os.environ["GEMINI_MODEL"]
        assert gemini_service.get_configured_model() == "gemini-3.8-flash"


def test_custom_gemini_model_override():
    """Verify that GEMINI_MODEL set in environment is respected."""
    with patch.dict("os.environ", {"GEMINI_MODEL": "custom-gemini-test-model"}, clear=False):
        assert gemini_service.get_configured_model() == "custom-gemini-test-model"


def test_all_modalities_use_configured_model_and_log(caplog):
    """Verify text, image, and audio all dispatch using the same configured model and log it."""
    import asyncio
    import logging
    
    calls = []
    
    with patch("app.gemini_service.get_gemini_client") as mock_client_factory:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.text = "Model test response"
        
        async def fake_generate(*args, **kwargs):
            calls.append((kwargs.get("model"), kwargs.get("contents")))
            return mock_response
            
        mock_client.aio.models.generate_content = fake_generate
        mock_client_factory.return_value = mock_client
        
        with caplog.at_level(logging.INFO):
            # 1. Text modality
            r_text = asyncio.run(gemini_service.generate_multimodal_response(message="Hello Study Buddy", modality="text"))
            # 2. Image modality
            r_image = asyncio.run(gemini_service.generate_multimodal_response(message="Explain diagram", media_bytes=VALID_PNG_HEADER, media_mime_type="image/png", modality="image"))
            # 3. Audio modality
            r_audio = asyncio.run(gemini_service.generate_multimodal_response(message="Summarize lecture", media_bytes=VALID_WAV_HEADER, media_mime_type="audio/wav", modality="audio"))
            
            configured_model = gemini_service.get_configured_model()
            assert configured_model == "gemini-3.8-flash"
            
            # Check models returned in normalized response
            assert r_text["model"] == "gemini-3.8-flash"
            assert r_image["model"] == "gemini-3.8-flash"
            assert r_audio["model"] == "gemini-3.8-flash"
            
            # Check models passed to official Gemini SDK
            assert len(calls) == 3
            assert calls[0][0] == "gemini-3.8-flash"
            assert calls[1][0] == "gemini-3.8-flash"
            assert calls[2][0] == "gemini-3.8-flash"
            
            # Verify log messages
            log_text = caplog.text
            assert "Dispatching Gemini request: model=gemini-3.8-flash, modality=text" in log_text
            assert "Dispatching Gemini request: model=gemini-3.8-flash, modality=image" in log_text
            assert "Dispatching Gemini request: model=gemini-3.8-flash, modality=audio" in log_text


