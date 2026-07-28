# Changelog

## v1.0.0 — 2026-07-28

Initial release.

**Chat**

- Streaming chat against a local Ollama server, with conversation history and a sidebar for switching between past conversations
- Markdown-lite rendering (bold, inline code, fenced code blocks)
- Regenerate and copy-last-reply actions
- File attachments — attach text-based files (code, logs, notes) for the model to read as part of your message

**Meetings**

- Microphone selection with a persisted preference and a one-click Test Microphone check
- Record-then-transcribe pipeline using a locally-bundled `faster-whisper` model — fully offline, with automatic GPU acceleration and CPU fallback
- Map-reduce summarization into structured notes (Key Points / Decisions / Action Items), scaling to arbitrarily long meetings
- Export to `.txt` and save-to-chat-history

**Distribution**

- Self-contained installer requiring no Python, conda, or command-line use
- Speech-to-text model bundled for fully offline transcription out of the box
- Configuration via a plain-text `config.json` for lab administrators, and an in-app Settings dialog for day-to-day server address changes

**Design**

- A custom visual theme (dark sidebar, color-coded action states, message bubbles) rather than default Tk styling
