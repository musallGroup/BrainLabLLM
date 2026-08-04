# Configuration

Most settings can be changed from **File → Settings** in the app (see [Settings](user-guide/settings.md)). This page documents the underlying `config.json` file, for lab administrators setting up a new machine or troubleshooting.

## Where it lives

`config.json` sits in the same folder as `BrainLabLLM.exe` (wherever the app was installed — by default `%LOCALAPPDATA%\Programs\BrainLabLLM\`). It's created automatically with default values the first time the app runs, if it doesn't already exist.

It's a plain text file — open it with Notepad, edit, save, and restart the app.

## Fields

```json title="config.json"
{
  "ollama_api_url": "http://10.3.2.112:11434/api/chat",
  "ollama_model": "qwen3.6:35b-coder",
  "whisper_model_size": "medium",
  "whisper_device": "auto"
}
```

| Field | Default | Description |
|---|---|---|
| `ollama_api_url` | *(lab-specific)* | Full URL to your Ollama server's `/api/chat` endpoint. Same as the Server Address field in Settings. |
| `ollama_model` | *(lab-specific)* | Model name to request from that server. Same as the Model Name field in Settings. |
| `whisper_model_size` | `medium` | Which [faster-whisper](https://github.com/SYSTRAN/faster-whisper) model size to use for transcription. The installed app bundles the `medium` model's weights for fully offline use — changing this to a size that isn't bundled will make the app try to download it from Hugging Face Hub on first use, which requires internet access. |
| `whisper_device` { #whisper_device } | `auto` | Controls GPU/CPU selection for transcription. `auto` tries the GPU first and falls back to CPU automatically if unavailable (recommended for shared lab machines with unknown hardware). `cuda` forces GPU use and fails loudly if none is available, rather than silently using CPU — useful for confirming GPU setup during installation. `cpu` forces CPU-only, useful for machines you know don't have a usable GPU, since it skips a few seconds of GPU-detection overhead on every recording. |

## Per-user data

Chat history and your last-selected microphone are stored separately from `config.json`, in `%APPDATA%\BrainLabLLM\` (`chats.json` and `settings.json`). This is deliberate: the app's install folder may not be writable by every user (especially if installed to a shared or admin-managed location), while `%APPDATA%` is always writable by the current user and keeps each person's history private on a shared machine.

## Resetting to defaults

Delete `config.json` and restart the app — a fresh one with default values will be created automatically.
