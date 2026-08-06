# Building from Source

## Prerequisites

- Windows 10/11
- [Miniconda or Anaconda](https://www.anaconda.com/docs/getting-started/miniconda/install)
- A local [Ollama](https://ollama.com) server reachable on your network, running a chat-capable model

## Set up the environment

```bash
conda create -n aider_env python=3.11 -y
conda activate aider_env
pip install requests sounddevice soundfile scipy numpy faster-whisper truststore pytest
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install pyannote.audio
```

!!! note "Windows SSL certificate bug"
    If `pip install` intermittently fails with `ASN1: NOT_ENOUGH_DATA` or similar SSL errors, this is a known CPython-on-Windows bug where a single malformed certificate in the Windows certificate store crashes Python's default SSL context. Installing `truststore` and adding a `sitecustomize.py` alongside your environment's site-packages containing:

    ```python
    import truststore
    truststore.inject_into_ssl()
    ```

    routes around it. One caveat: this can conflict with `pip`'s own vendored copy of `truststore` during large dependency resolutions (a `RecursionError` deep in SSL handling) — if that happens, temporarily rename `sitecustomize.py` for the duration of the `pip install`, then restore it.

!!! note "torch must be the CUDA build, not CPU-only"
    Plain `pip install torch` grabs a CPU-only wheel, which makes `torch.cuda.is_available()` return `False` even with a working GPU — this silently breaks speaker identification (see [Architecture](../architecture.md#speaker-diarization)), since it's gated on that check. Always install torch from the `cu1xx` index matching your driver, as shown above (check with `nvidia-smi`; the index only needs to be *at or below* what your driver supports, not an exact match).

!!! note "Speaker identification needs a Hugging Face token in dev mode"
    `pyannote/speaker-diarization-community-1` is a gated model — accept its terms at [huggingface.co](https://huggingface.co/pyannote/speaker-diarization-community-1) and generate a token at `hf.co/settings/tokens`, then set `HUGGINGFACE_TOKEN` in your environment before running from source. This is a one-time step for whoever builds the packaged app: the model gets bundled into the exe the same way the Whisper model is, so end users never need a token or an account.

## Run it

```bash
python main.py
```

`config.json` and `chats.json` will be created automatically on first run (see [Configuration](../configuration.md)).

## Project structure

```
BrainLabLLM/
├── main.py           # Tkinter UI, chat networking, summarization
├── meeting.py         # Audio recording + transcription (no UI dependency)
├── diarization.py      # Speaker identification (no UI dependency)
├── agent.py             # Coding-agent tool-calling loop (no UI dependency)
├── wiki.py               # Lab wiki lookup tool (no UI dependency)
├── websearch.py            # Public web search tool via local SearXNG (no UI dependency)
├── theme.py                  # Color palette + ttk.Style setup
├── installer.py                # Standalone installer GUI (built separately)
├── app_icon.ico                  # App icon, used for both the exe and window icon
├── tests/                          # Automated pytest suite
├── packaging/                     # Tracked sources for files assembled into dist/ at build time
├── mkdocs.yml                       # This documentation site's configuration
└── docs/                              # This documentation site's content
```

## Running the standalone test scripts

`meeting.py` includes a `_console_test()` function for validating the audio → transcription pipeline without the GUI:

```bash
python meeting.py
```

This records from your default microphone for 30 seconds and prints the transcript — useful for isolating microphone or GPU issues from UI issues.

## Next steps

- [Packaging & Distribution](packaging.md) — turning this into the installer end users get
- [Contributing](contributing.md) — code conventions and how to propose changes
