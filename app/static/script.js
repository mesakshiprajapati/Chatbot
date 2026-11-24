/**
 * Study Buddy Chat - Frontend Application
 * Handles chat interactions, multimodal file attachments,
 * safe markdown rendering, and error recovery.
 */

(function () {
  "use strict";

  // State
  let conversationHistory = [];
  let selectedFile = null; // { file: File, type: 'image' | 'audio', previewUrl: string | null }
  let isSubmitting = false;
  let lastFailedPrompt = null; // { message: string, file: File | null, type: string | null }

  // DOM Elements
  const chatMain = document.getElementById("chatMain");
  const emptyState = document.getElementById("emptyState");
  const messagesList = document.getElementById("messagesList");
  const typingIndicator = document.getElementById("typingIndicator");

  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const clearChatBtn = document.getElementById("clearChatBtn");

  const attachImageBtn = document.getElementById("attachImageBtn");
  const attachAudioBtn = document.getElementById("attachAudioBtn");
  const imageInput = document.getElementById("imageInput");
  const audioInput = document.getElementById("audioInput");

  const attachmentTray = document.getElementById("attachmentTray");
  const attachmentPreviewContent = document.getElementById("attachmentPreviewContent");
  const removeAttachmentBtn = document.getElementById("removeAttachmentBtn");

  const notificationBanner = document.getElementById("notificationBanner");
  const bannerMessage = document.getElementById("bannerMessage");
  const bannerRetryBtn = document.getElementById("bannerRetryBtn");
  const bannerDismissBtn = document.getElementById("bannerDismissBtn");

  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");
  const modelBadge = document.getElementById("modelBadge");

  // Limits (aligned with backend)
  const MAX_IMAGE_BYTES = 5 * 1024 * 1024; // 5 MB
  const MAX_AUDIO_BYTES = 15 * 1024 * 1024; // 15 MB
  const ALLOWED_IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".webp"];
  const ALLOWED_AUDIO_EXTS = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm"];

  // ==========================================================================
  // Initialization & Health Check
  // ==========================================================================
  async function checkServerHealth() {
    try {
      const response = await fetch("/api/health");
      if (!response.ok) throw new Error("Health check failed");
      const data = await response.json();

      if (data.model) {
        modelBadge.textContent = data.model;
      }

      if (data.api_key_configured) {
        statusDot.className = "status-dot online";
        statusText.textContent = "Online";
      } else {
        statusDot.className = "status-dot warning";
        statusText.textContent = "API Key Needed";
        showNotification(
          "Gemini API key is not configured. Add GEMINI_API_KEY to your .env file to enable AI answers.",
          "warning",
          false
        );
      }
    } catch (err) {
      statusDot.className = "status-dot offline";
      statusText.textContent = "Offline";
      console.warn("Unable to contact backend:", err);
    }
  }

  // ==========================================================================
  // Notification Banner Helpers
  // ==========================================================================
  function showNotification(message, type = "error", showRetry = false) {
    bannerMessage.textContent = message;
    notificationBanner.className = `notification-banner ${type}`;
    bannerRetryBtn.style.display = showRetry ? "inline-flex" : "none";
    notificationBanner.style.display = "flex";
  }

  function hideNotification() {
    notificationBanner.style.display = "none";
    bannerRetryBtn.style.display = "none";
  }

  bannerDismissBtn.addEventListener("click", hideNotification);

  bannerRetryBtn.addEventListener("click", () => {
    hideNotification();
    if (lastFailedPrompt) {
      const { message, file, type } = lastFailedPrompt;
      if (file) {
        setAttachment(file, type);
      }
      messageInput.value = message;
      updateSendButtonState();
      handleSubmit();
    }
  });

  // ==========================================================================
  // Textarea Auto-Resize & Input Handling
  // ==========================================================================
  function adjustTextareaHeight() {
    messageInput.style.height = "auto";
    const newHeight = Math.min(messageInput.scrollHeight, 160);
    messageInput.style.height = newHeight + "px";
  }

  function updateSendButtonState() {
    const hasText = messageInput.value.trim().length > 0;
    const hasFile = selectedFile !== null;
    sendBtn.disabled = (!hasText && !hasFile) || isSubmitting;
  }

  messageInput.addEventListener("input", () => {
    adjustTextareaHeight();
    updateSendButtonState();
  });

  messageInput.addEventListener("keydown", (e) => {
    // Send on Enter (without Shift)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled && !isSubmitting) {
        handleSubmit();
      }
    }
  });

  // Quick prompt cards
  document.querySelectorAll(".quick-prompt-card").forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.getAttribute("data-prompt");
      if (prompt) {
        messageInput.value = prompt;
        adjustTextareaHeight();
        updateSendButtonState();
        messageInput.focus();
      }
    });
  });

  // ==========================================================================
  // File Attachment Handling
  // ==========================================================================
  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function getFileExtension(filename) {
    return filename.slice((filename.lastIndexOf(".") - 1 >>> 0) + 2).toLowerCase();
  }

  function setAttachment(file, type) {
    // Clear previous object URL if any
    if (selectedFile && selectedFile.previewUrl) {
      URL.revokeObjectURL(selectedFile.previewUrl);
    }

    let previewUrl = null;
    if (type === "image") {
      previewUrl = URL.createObjectURL(file);
    }

    selectedFile = { file, type, previewUrl };

    // Render Preview
    attachmentPreviewContent.innerHTML = "";
    if (type === "image") {
      const img = document.createElement("img");
      img.src = previewUrl;
      img.alt = file.name;
      img.className = "attachment-thumbnail";
      attachmentPreviewContent.appendChild(img);
    } else {
      const icon = document.createElement("div");
      icon.className = "attachment-audio-icon";
      icon.innerHTML = "🎙️";
      icon.setAttribute("aria-hidden", "true");
      attachmentPreviewContent.appendChild(icon);
    }

    const info = document.createElement("div");
    info.className = "attachment-info";

    const nameSpan = document.createElement("span");
    nameSpan.className = "attachment-filename";
    nameSpan.textContent = file.name;

    const sizeSpan = document.createElement("span");
    sizeSpan.className = "attachment-filesize";
    sizeSpan.textContent = `${type.toUpperCase()} • ${formatBytes(file.size)}`;

    info.appendChild(nameSpan);
    info.appendChild(sizeSpan);
    attachmentPreviewContent.appendChild(info);

    attachmentTray.style.display = "block";
    updateSendButtonState();
  }

  function removeAttachment() {
    if (selectedFile && selectedFile.previewUrl) {
      URL.revokeObjectURL(selectedFile.previewUrl);
    }
    selectedFile = null;
    imageInput.value = "";
    audioInput.value = "";
    attachmentTray.style.display = "none";
    attachmentPreviewContent.innerHTML = "";
    updateSendButtonState();
  }

  removeAttachmentBtn.addEventListener("click", removeAttachment);

  // Trigger file inputs
  attachImageBtn.addEventListener("click", () => {
    imageInput.click();
  });

  attachAudioBtn.addEventListener("click", () => {
    audioInput.click();
  });

  // Handle Image selection
  imageInput.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    const ext = "." + getFileExtension(file.name);
    if (!ALLOWED_IMAGE_EXTS.includes(ext)) {
      showNotification(`Invalid image format (${ext}). Supported formats: JPG, PNG, WebP.`, "error");
      imageInput.value = "";
      return;
    }

    if (file.size > MAX_IMAGE_BYTES) {
      showNotification(`Image is too large (${formatBytes(file.size)}). Maximum size is 5 MB.`, "error");
      imageInput.value = "";
      return;
    }

    hideNotification();
    setAttachment(file, "image");
  });

  // Handle Audio selection
  audioInput.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    const ext = "." + getFileExtension(file.name);
    if (!ALLOWED_AUDIO_EXTS.includes(ext)) {
      showNotification(`Invalid audio format (${ext}). Supported formats: MP3, WAV, M4A, AAC, OGG, FLAC, WebM.`, "error");
      audioInput.value = "";
      return;
    }

    if (file.size > MAX_AUDIO_BYTES) {
      showNotification(`Audio is too large (${formatBytes(file.size)}). Maximum size is 15 MB.`, "error");
      audioInput.value = "";
      return;
    }

    hideNotification();
    setAttachment(file, "audio");
  });

  // ==========================================================================
  // Safe Markdown / Output Sanitizer
  // Treats model output as untrusted text; escapes HTML first.
  // ==========================================================================
  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderSafeMarkdown(rawText) {
    if (!rawText) return "";

    // Step 1: Escape all raw HTML to prevent XSS
    let escaped = escapeHtml(rawText);

    // Step 2: Extract code blocks to preserve formatting and prevent nested replacements
    const codeBlocks = [];
    escaped = escaped.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
      codeBlocks.push(`<pre><code>${code.trim()}</code></pre>`);
      return placeholder;
    });

    // Step 3: Inline code `code`
    escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Step 4: Headings (###, ##, #)
    escaped = escaped.replace(/^### (.*$)/gim, "<h3>$1</h3>");
    escaped = escaped.replace(/^## (.*$)/gim, "<h2>$1</h2>");
    escaped = escaped.replace(/^# (.*$)/gim, "<h1>$1</h1>");

    // Step 5: Bold and Italic
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    escaped = escaped.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Step 6: Lists
    // Unordered lists (- or *)
    escaped = escaped.replace(/^\s*[-*]\s+(.*)$/gim, "<li>$1</li>");
    escaped = escaped.replace(/(<li>.*<\/li>(\n|$)(\s*))+/g, "<ul>$&</ul>");

    // Ordered lists (1. 2.)
    escaped = escaped.replace(/^\s*\d+\.\s+(.*)$/gim, "<oli>$1</oli>");
    escaped = escaped.replace(/(<oli>.*<\/oli>(\n|$)(\s*))+/g, (match) => {
      return "<ol>" + match.replace(/<oli>/g, "<li>").replace(/<\/oli>/g, "</li>") + "</ol>";
    });

    // Step 7: Paragraphs & line breaks (double newline = paragraph, single = <br>)
    // Avoid breaking inside tags
    const paragraphs = escaped.split(/\n{2,}/);
    escaped = paragraphs
      .map((p) => {
        p = p.trim();
        if (!p) return "";
        if (p.startsWith("<h") || p.startsWith("<ul") || p.startsWith("<ol") || p.startsWith("__CODE_BLOCK_")) {
          return p;
        }
        return `<p>${p.replace(/\n/g, "<br>")}</p>`;
      })
      .join("\n");

    // Step 8: Re-insert code blocks
    codeBlocks.forEach((block, index) => {
      escaped = escaped.replace(`__CODE_BLOCK_${index}__`, block);
    });

    return escaped;
  }

  // ==========================================================================
  // Chat UI Rendering
  // ==========================================================================
  function scrollToBottom() {
    chatMain.scrollTop = chatMain.scrollHeight;
  }

  function appendUserMessage(text, attachment) {
    if (emptyState.style.display !== "none") {
      emptyState.style.display = "none";
      messagesList.style.display = "flex";
    }

    const row = document.createElement("div");
    row.className = "message-row user-row";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "👤";
    avatar.setAttribute("aria-hidden", "true");

    const content = document.createElement("div");
    content.className = "message-content";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    // If attachment exists, show preview inside user bubble
    if (attachment) {
      const attachDiv = document.createElement("div");
      attachDiv.className = "message-attachment-preview";

      if (attachment.type === "image" && attachment.previewUrl) {
        const img = document.createElement("img");
        img.src = attachment.previewUrl;
        img.alt = "Uploaded image";
        img.className = "message-attachment-image";
        attachDiv.appendChild(img);
      } else if (attachment.type === "audio") {
        const audioBadge = document.createElement("div");
        audioBadge.className = "message-attachment-audio-badge";
        audioBadge.innerHTML = `<span>🎙️</span> <span>${escapeHtml(attachment.file.name)}</span>`;
        attachDiv.appendChild(audioBadge);
      }
      bubble.appendChild(attachDiv);
    }

    if (text) {
      const textP = document.createElement("p");
      textP.textContent = text;
      bubble.appendChild(textP);
    }

    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    content.appendChild(bubble);
    content.appendChild(meta);

    row.appendChild(avatar);
    row.appendChild(content);

    messagesList.appendChild(row);
    scrollToBottom();
  }

  function appendAiMessage(rawText, modality, modelName) {
    const row = document.createElement("div");
    row.className = "message-row ai-row";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "🎓";
    avatar.setAttribute("aria-hidden", "true");

    const content = document.createElement("div");
    content.className = "message-content";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = renderSafeMarkdown(rawText);

    const meta = document.createElement("div");
    meta.className = "message-meta";
    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const modLabel = modality ? ` • ${modality.toUpperCase()}` : "";
    meta.textContent = `${modelName || "Gemini"}${modLabel} • ${timeStr}`;

    content.appendChild(bubble);
    content.appendChild(meta);

    row.appendChild(avatar);
    row.appendChild(content);

    messagesList.appendChild(row);
    scrollToBottom();
  }

  // ==========================================================================
  // Submission & API Communication
  // ==========================================================================
  async function handleSubmit() {
    const text = messageInput.value.trim();
    const currentAttachment = selectedFile;

    // Validate non-empty
    if (!text && !currentAttachment) {
      return;
    }

    if (isSubmitting) return;

    // Set submitting state
    isSubmitting = true;
    updateSendButtonState();
    attachImageBtn.disabled = true;
    attachAudioBtn.disabled = true;
    clearChatBtn.disabled = true;
    hideNotification();

    // Preserve prompt details in case of failure
    lastFailedPrompt = {
      message: text,
      file: currentAttachment ? currentAttachment.file : null,
      type: currentAttachment ? currentAttachment.type : null,
    };

    // Render user message in chat
    appendUserMessage(text, currentAttachment);

    // Show typing indicator
    typingIndicator.style.display = "flex";
    scrollToBottom();

    // Prepare FormData
    const formData = new FormData();
    if (text) {
      formData.append("message", text);
    }
    if (currentAttachment && currentAttachment.file) {
      formData.append("file", currentAttachment.file);
    }
    if (conversationHistory.length > 0) {
      formData.append("conversation_history", JSON.stringify(conversationHistory));
    }

    // Reset input fields in UI
    messageInput.value = "";
    adjustTextareaHeight();
    removeAttachment();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        const errorMsg = data.error || `Server returned error (${response.status})`;
        throw new Error(errorMsg);
      }

      // Successful reply
      const reply = data.reply;
      const model = data.model;
      const modality = data.modality;

      // Update conversation history for follow-ups
      // Record user turn (with fallback prompt label if user sent media only)
      const userTurnText = text || (currentAttachment?.type === "image" ? "[Uploaded study image]" : "[Uploaded study audio]");
      conversationHistory.push({ role: "user", text: userTurnText });
      conversationHistory.push({ role: "model", text: reply });

      // Render reply in chat
      appendAiMessage(reply, modality, model);

      // Clear failed prompt state on success
      lastFailedPrompt = null;
    } catch (err) {
      console.error("Submission failed:", err);
      // Restore user input into textarea so nothing is lost!
      messageInput.value = text;
      adjustTextareaHeight();

      // Show error banner with retry option
      showNotification(err.message || "Failed to get AI response. Please try again.", "error", true);
    } finally {
      typingIndicator.style.display = "none";
      isSubmitting = false;
      attachImageBtn.disabled = false;
      attachAudioBtn.disabled = false;
      clearChatBtn.disabled = false;
      updateSendButtonState();
      messageInput.focus();
    }
  }

  sendBtn.addEventListener("click", () => {
    if (!sendBtn.disabled && !isSubmitting) {
      handleSubmit();
    }
  });

  // ==========================================================================
  // Clear Chat History
  // ==========================================================================
  clearChatBtn.addEventListener("click", () => {
    if (conversationHistory.length === 0 && (!messagesList.children || messagesList.children.length === 0)) {
      return;
    }

    if (confirm("Are you sure you want to clear this study conversation?")) {
      conversationHistory = [];
      messagesList.innerHTML = "";
      messagesList.style.display = "none";
      emptyState.style.display = "block";
      removeAttachment();
      hideNotification();
      lastFailedPrompt = null;
      messageInput.value = "";
      adjustTextareaHeight();
      updateSendButtonState();
    }
  });

  // Run initial server check
  checkServerHealth();
})();
