# Study Buddy Chat - System Specification (SPEC.md)

## 1. Overview
"Study Buddy Chat" is a multimodal AI study assistant powered by Google Gemini API, FastAPI, and a responsive vanilla HTML/CSS/JavaScript frontend. It enables students to chat via text, upload study diagrams/photos for analysis, and submit lecture/study audio clips for transcription and summarization, all within a unified, interactive chat interface.

---

## 2. Functional Requirements

### F1: Text Chat & Multi-Turn Conversation
- **F1.1 Message Submission**: Users can submit plain-text questions, prompts, or homework queries.
- **F1.2 Contextual Memory (Follow-ups)**: The client tracks conversation turns (user and assistant messages) and submits the relevant history with subsequent requests so Gemini can answer follow-up questions contextually.
- **F1.3 Streaming/Normalized Output**: The backend returns normalized JSON containing the assistant's reply, active model, detected modality, and timestamp.
- **F1.4 Empty Input Guard**: The client and server reject empty or whitespace-only message submissions when no attachment is attached.

### F2: Image Understanding (Visual Study Aid)
- **F2.1 Supported Formats**: JPEG (`.jpg`, `.jpeg`), PNG (`.png`), and WebP (`.webp`).
- **F2.2 Single Attachment**: Users can attach one image per prompt.
- **F2.3 Client-Side Preview**: An image thumbnail preview with file details and a remove button is displayed before sending.
- **F2.4 Optional Prompt**: Users can submit an image with an optional accompanying question or study instruction. If no prompt is entered, the system applies a default study prompt (e.g., *"Please analyze and explain this study material or diagram in detail."*).
- **F2.5 Transient In-Memory Processing**: Uploaded images are validated in-memory and passed as raw byte parts to Gemini; files are never stored permanently on disk.

### F3: Audio Understanding (Audio Notes & Lectures)
- **F3.1 Supported Formats**: MP3 (`.mp3`), WAV (`.wav`), M4A (`.m4a`), AAC (`.aac`), OGG (`.ogg`), FLAC (`.flac`), WebM (`.webm`).
- **F3.2 Single Attachment**: Users can attach one audio recording per prompt.
- **F3.3 Client-Side Audio Badge**: An audio attachment preview indicating file name, size, and a remove button is displayed before sending.
- **F3.4 Optional Prompt**: Users can submit audio with an optional question. If omitted, the system applies a default prompt (e.g., *"Please transcribe and provide a clear summary with key study takeaways from this audio."*).
- **F3.5 Transient Processing**: Audio is verified in-memory (size, extension, header check) and passed directly to the Gemini API.

### F4: Modern Interactive UI
- **F4.1 Shared Chat Stream**: All modalities (text, image, audio) share a single conversational stream with role-based chat bubbles.
- **F4.2 Attachment Display in Chat**: Submitted user messages display an inline thumbnail of the uploaded image or an audio indicator alongside the prompt text.
- **F4.3 Loading & Typing Indicators**: An animated typing indicator and disabled send controls inform the user while the model is thinking.
- **F4.4 Error Feedback & Retry**: Clear inline error notifications for network failures, oversized files, missing API keys, or provider errors, with a "Retry" button that restores the last failed prompt without losing user input.
- **F4.5 Empty State & Quick Prompts**: When the chat is empty, helpful study prompt suggestions (e.g., "Explain Photosynthesis", "Summarize my notes", "Analyze a math problem") are displayed.
- **F4.6 Clear & Reset Option**: A button to clear current conversation history and start fresh.

---

## 3. Non-Functional Requirements

### N1: Security & Privacy
- **N1.1 Server-Side Secrets**: `GEMINI_API_KEY` is loaded from `.env` via `python-dotenv` and strictly kept on the server. Never exposed to the frontend, client logs, or repository.
- **N1.2 Strict File Validation**: Server validates file size limits (5 MB for images, 15 MB for audio), allowed extensions, declared MIME types, and magic byte signatures to prevent malicious uploads or corrupted files.
- **N1.3 No Permanent Storage**: Media is held transiently in memory for the duration of the API call and immediately garbage-collected. No media files or raw buffers are written to disk or recorded in server logs.
- **N1.4 Output Sanitization**: Model replies and user messages are treated as untrusted text. Text is rendered using safe DOM text content and HTML escaping (never raw `innerHTML` execution) to mitigate XSS risks.
- **N1.5 Privacy Transparency**: The user interface contains a clear notice informing users that queries and media attachments are processed using Google's Gemini API.

### N2: Performance & Reliability
- **N2.1 Provider Timeouts**: Outgoing Gemini API calls have an enforced timeout (default: 30 seconds) to prevent hanging requests.
- **N2.2 Duplicate Submission Prevention**: Send buttons and input fields are disabled immediately upon submission and remain locked until the response or an error arrives.
- **N2.3 Graceful Error Handling**: Distinct error codes and user-friendly messages for missing API keys, rate limit/quota exhaustion (429), timeouts, and invalid media.
- **N2.4 Lightweight Architecture**: Minimal Python dependencies (FastAPI, Uvicorn, python-dotenv, google-genai, python-multipart). Zero Node.js/npm dependencies.

### N3: Usability & Accessibility
- **N3.1 Responsive Layout**: Seamless experience across mobile (320px+), tablet, and desktop viewports.
- **N3.2 Accessible Controls**: Semantic HTML, distinct ARIA labels, visual focus indicators, and keyboard navigation support (`Enter` to send, `Shift+Enter` for multiline).
- **N3.3 State Preservation**: If an error occurs, the user's input text is preserved in the input box so the user does not need to retype their message.

---

## 4. Architecture & Data Flow

```mermaid
flowchart TD
    User["Student (Browser UI)"] -->|Text / Image / Audio| FastAPI["FastAPI Backend (app/main.py)"]
    FastAPI -->|1. Validate MIME / Size / Magic Bytes| Validator["Media Validator"]
    FastAPI -->|2. Format Prompt & History| GeminiService["Gemini Service (app/gemini_service.py)"]
    GeminiService -->|3. google-genai SDK (GEMINI_API_KEY)| GeminiAPI["Google Gemini API (gemini-3.8-flash)"]
    GeminiAPI -->|4. Response text| GeminiService
    GeminiService -->|5. Structured Result| FastAPI
    FastAPI -->|6. JSON Response| User
```

---

## 5. API Specification

### `GET /api/health`
Returns system status and whether `GEMINI_API_KEY` is configured.
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "api_key_configured": true,
    "model": "gemini-3.8-flash",
    "max_image_size_mb": 5,
    "max_audio_size_mb": 15
  }
  ```

### `POST /api/chat`
Multimodal endpoint accepting `multipart/form-data`.
- **Form Fields**:
  - `message` (string, optional if file present): The user's prompt.
  - `file` (binary, optional): Image or audio file upload.
  - `conversation_history` (string, optional): JSON-encoded array of previous turns: `[{"role": "user", "text": "..."}, {"role": "model", "text": "..."}]`.
- **Response `200 OK`**:
  ```json
  {
    "success": true,
    "reply": "Here is the explanation...",
    "model": "gemini-3.8-flash",
    "modality": "text" | "image" | "audio",
    "timestamp": "2026-11-24T16:00:00Z"
  }
  ```
- **Response `400 / 422 / 500 / 503`**:
  ```json
  {
    "success": false,
    "error": "Descriptive human-readable error message",
    "error_type": "validation_error" | "auth_error" | "quota_error" | "timeout_error" | "provider_error"
  }
  ```
