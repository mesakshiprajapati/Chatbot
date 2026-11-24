# 🎓 Study Buddy Chat

A multimodal AI study assistant powered by **Google Gemini API** (`google-genai` SDK), **FastAPI**, and a responsive **HTML, CSS, and Vanilla JavaScript** frontend. 

Study Buddy Chat enables students to ask questions via text, attach diagrams and homework images for visual analysis, and upload study/lecture audio clips for transcription and structured summaries—all within a single, unified conversation interface.

---

## 📋 Table of Contents
1. [Tech Stack](#-tech-stack)
2. [Project Structure](#-project-structure)
3. [Features & Modalities](#-features--modalities)
4. [Security & Privacy](#-security--privacy)
5. [Prerequisites & Installation](#-prerequisites--installation)
6. [Environment Variables](#-environment-variables)
7. [Running the Application](#-running-the-application)
8. [Automated Testing](#-automated-testing)
9. [Manual Test Checklist (MT-01 to MT-12)](#-manual-test-checklist-mt-01-to-mt-12)
10. [Walkthrough & Verification Guide](#-walkthrough--verification-guide)
11. [Supported Formats & Size Limits](#-supported-formats--size-limits)
12. [Known Limitations](#-known-limitations)

---

## 🛠 Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **AI SDK**: Official `google-genai` Python SDK
- **Environment**: `python-dotenv`
- **Frontend**: Semantic HTML5, CSS3 (responsive, dark/light aware), Vanilla JavaScript (ES6+)
- **Testing**: `pytest`, `httpx`
- **Strict Constraints**: No Node.js, No npm, No React, No database, No external UI frameworks.

---

## 📁 Project Structure

```
Study-Buddy-Chatbot/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application, routing, and media validation
│   ├── gemini_service.py    # Dedicated Gemini SDK module (client, models, prompt formatting)
│   └── static/
│       ├── index.html       # Single-page application markup
│       ├── style.css        # Responsive, accessible stylesheet
│       └── script.js        # Vanilla JS client (chat state, file handling, safe markdown)
├── tests/
│   ├── __init__.py
│   └── test_study_buddy.py  # 15 automated unit & integration tests
├── .env.example             # Template for environment variables
├── .gitignore               # Excludes secrets, bytecode, and virtual environments
├── requirements.txt         # Production and development dependencies
├── SPEC.md                  # Comprehensive functional & non-functional requirements
└── README.md                # Setup, usage, test checklist, and documentation
```

---

## 🌟 Features & Modalities

### 1. 💬 Text Understanding & Multi-turn Chat
- Ask homework or study questions and receive step-by-step explanations.
- Tracks conversation history so you can ask contextual follow-up questions.
- Built-in quick prompt cards on empty state for rapid exploration.

### 2. 🖼️ Image Understanding
- Upload study diagrams, handwritten notes, textbook pages, or geometry problems.
- Supports JPEG (`.jpg`, `.jpeg`), PNG (`.png`), and WebP (`.webp`).
- Live client-side thumbnail preview with file size details and removal button.
- Optional prompt: You can ask a specific question (e.g. *"What is step 3 in this calculation?"*), or omit the prompt to use the default comprehensive analysis prompt.

### 3. 🎙️ Audio Understanding
- Upload lecture recordings, study voice notes, or spoken summaries.
- Supports MP3, WAV, M4A, AAC, OGG, FLAC, and WebM.
- Visual audio indicator with file details and removal button.
- Optional prompt: Ask for a specific summary or let Study Buddy provide a full transcription with key study points.

### 4. 🎨 Modern, Accessible Interface
- Chat bubbles with user message styling and AI tutor styling.
- Safe Markdown rendering (bold, italics, code blocks, lists, headings) with strict HTML escaping to prevent XSS.
- Animated typing indicator while Gemini is generating answers.
- Preserves user input in the text box upon error so nothing is lost.
- Inline notification banner with a one-click **"Retry"** button.
- Reset button to clear conversation history.

---

## 🔒 Security & Privacy

1. **Server-Side API Key**: The `GEMINI_API_KEY` is loaded from `.env` on the server and is never exposed in frontend code, URLs, client responses, or logs.
2. **Strict File Validation**:
   - Files are validated against allowed extensions and declared MIME types.
   - **Magic Bytes Validation**: File headers are inspected to verify that files are genuine images or audio (preventing renamed executable files or corrupted data).
   - Strict size caps: **5 MB** for images, **15 MB** for audio.
3. **Zero Permanent Media Storage**: Uploaded images and audio are held strictly in memory during validation and forwarded directly to the Gemini API via `types.Part.from_bytes()`. No media files or raw buffers are written to disk.
4. **Untrusted Model Output Sanitization**: AI responses and user text are treated as untrusted text. All HTML entities (`&`, `<`, `>`, `"`, `'`) are escaped before Markdown rendering, preventing XSS.
5. **Transparency**: The UI features an upfront notice informing students that media is processed transiently via Google's Gemini API.

---

## 🚀 Prerequisites & Installation

### 1. Clone or Open Workspace
Open a PowerShell terminal in the project directory (`d:\Study-Buddy-Chatbot`).

### 2. Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Open `.env` in any text editor and insert your Gemini API key:
```env
# Gemini API Configuration (Get your free key at https://aistudio.google.com/)
GEMINI_API_KEY=your_actual_gemini_api_key_here

# Optional: Default model (gemini-3.8-flash is default)
GEMINI_MODEL=gemini-3.8-flash

# Optional: Server host and port
HOST=127.0.0.1
PORT=8000
```

> **Note**: If `GEMINI_API_KEY` is missing or contains placeholder text, the server runs gracefully, marks the status badge as "API Key Needed", and returns clear 401 instructions when a user submits a prompt.

---

## 💻 Running the Application

Start the FastAPI server using Uvicorn:

```powershell
# Run with auto-reload enabled
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
👉 **`http://127.0.0.1:8000`**

---

## 🧪 Automated Testing

A comprehensive automated test suite is included in `tests/test_study_buddy.py`. It covers:
- Root page serving and health checks
- Empty and whitespace submission rejection
- Unsupported file extension rejection
- Corrupted image/audio magic bytes rejection
- Oversized image (>5MB) and audio (>15MB) rejection
- Missing API key 401 handling
- Text, Image, and Audio multimodal response generation (mocked Gemini service)
- Provider quota (429) and timeout (504) error handling

Run the test suite with:
```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\pytest.exe tests/test_study_buddy.py -v
```

Expected result:
```
============================= 15 passed in 2.33s ==============================
```

---

## 📋 Manual Test Checklist (MT-01 to MT-12)

| Test ID | Test Scenario | Steps to Perform | Expected Result | Status |
|:---|:---|:---|:---|:---|
| **MT-01** | **App Startup** | Run `uvicorn app.main:app`. Open `http://127.0.0.1:8000`. | Page loads with header, empty state cards, and status badge ("Online" or "API Key Needed"). | Verified |
| **MT-02** | **Text Success** | Type *"Explain Newton's First Law"* and press Enter or Send. | Message appears in user bubble; typing indicator shows; AI responds with structured explanation. | Verified |
| **MT-03** | **Empty Text Guard** | Leave input blank and press Enter or click Send. | Send button is disabled; pressing Enter does not trigger submission. | Verified |
| **MT-04** | **Follow-up Messages** | After MT-02, ask *"Can you give a sports example of that?"*. | AI remembers the context of Newton's First Law and explains with soccer/baseball examples. | Verified |
| **MT-05** | **Image Success** | Click "Image", select a JPG/PNG/WebP diagram, type optional question, click Send. | Thumbnail preview displays before sending; bubble shows image thumbnail; AI describes diagram. | Verified |
| **MT-06** | **Invalid/Oversized Image** | Try selecting a file > 5MB, or rename a `.txt` file to `.png` and send. | Client/server catches error; banner explains "Image too large" or "corrupted or invalid". Input is preserved. | Verified |
| **MT-07** | **Audio Success** | Click "Audio", select a `.mp3` or `.wav` recording, click Send. | Audio badge shows file details; AI returns transcription and structured summary notes. | Verified |
| **MT-08** | **Invalid/Oversized Audio** | Try uploading an audio file > 15MB, or corrupted non-audio bytes. | Upload rejected with descriptive error message (413 or 400). Input is preserved. | Verified |
| **MT-09** | **Provider Failure & Retry** | Trigger an error (e.g. invalid key or network timeout). | Notification banner displays error with "Retry" button. Clicking "Retry" resubmits preserved input. | Verified |
| **MT-10** | **Duplicate Submission Guard** | Click Send rapidly on any valid prompt. | Send and attachment buttons are disabled immediately during submission; no duplicate requests sent. | Verified |
| **MT-11** | **Keyboard Accessibility** | Use `Tab` to navigate controls, `Enter` to send, `Shift+Enter` for multiline input. | All controls are focusable with visible focus rings; textarea auto-expands and supports multi-line. | Verified |
| **MT-12** | **API-Key Security** | Inspect browser DevTools (Network, Console, Elements, Sources) and git repository. | No API keys visible in frontend files or network payloads; `.env` is ignored in `.gitignore`. | Verified |

---

## 📸 Walkthrough & Verification Guide

### 1. Verification of the Chat Interface
1. Launch `http://127.0.0.1:8000`.
2. Observe the greeting and four quick-prompt study cards.
3. Click any prompt card (e.g., *"Mitosis vs. Meiosis comparison"*). Notice how it populates the textarea and enables the send button.
4. Click the Send button or press `Enter`. Watch the typing animation and the rendered markdown response.

### 2. Testing Image Understanding
1. Click the **Image** button.
2. Select any study diagram or textbook photo (e.g., `heart.png`).
3. Notice the attachment tray showing the thumbnail, filename, and file size.
4. (Optional) Type *"Explain the labels in this diagram"*, or leave the text box blank.
5. Click Send. The user bubble displays the thumbnail, and Gemini returns an educational explanation.

### 3. Testing Audio Understanding
1. Click the **Audio** button.
2. Select an audio file (e.g., `lecture.mp3` or `notes.wav`).
3. Notice the audio attachment card with the microphone icon.
4. Click Send. Gemini analyzes the audio and returns key lecture takeaways and study notes.

### 4. Testing Error Recovery
1. If your API key is invalid or unset, send a message.
2. An error banner will appear explaining the issue.
3. Notice that your typed text is preserved in the textarea.
4. Click the **"Retry"** button on the banner to easily re-attempt the request after fixing your configuration.

---

## 📊 Supported Formats & Size Limits

| Modality | Allowed File Formats | Max File Size | Validation Method |
|:---|:---|:---|:---|
| **Text** | Plain text (UTF-8) | 4,000 chars | Non-empty whitespace check |
| **Image** | `.jpg`, `.jpeg`, `.png`, `.webp` | **5 MB** | Extension, MIME type & Magic Byte signature check |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac`, `.webm` | **15 MB** | Extension, MIME type & Magic Byte/Container check |

---

## ⚠️ Known Limitations

1. **In-Memory Session Context**: Conversation history is maintained on the client for the duration of the browser tab session. Refreshing the browser starts a clean session.
2. **Transient Media Forwarding**: Media files are sent directly to the Google Gemini API in-memory and are not persisted to a local database or filesystem.
3. **Provider Rate Limits**: Gemini API free tier accounts are subject to Google's standard RPM (requests per minute) and TPM (tokens per minute) rate limits. If exceeded, the application displays a friendly rate limit notification.
