# Building from Source

## Prerequisites

- Windows 10/11
- [Miniconda or Anaconda](https://www.anaconda.com/docs/getting-started/miniconda/install)
- A local [Ollama](https://ollama.com) server reachable on your network, running a chat-capable model

## Set up the environment

```bash
conda create -n aider_env python=3.11 -y
conda activate aider_env
pip install requests sounddevice soundfile scipy numpy faster-whisper truststore
```

!!! note "Windows SSL certificate bug"
    If `pip install` intermittently fails with `ASN1: NOT_ENOUGH_DATA` or similar SSL errors, this is a known CPython-on-Windows bug where a single malformed certificate in the Windows certificate store crashes Python's default SSL context. Installing `truststore` and adding a `sitecustomize.py` alongside your environment's site-packages containing:

    ```python
    import truststore
    truststore.inject_into_ssl()
    ```

    routes around it. One caveat: this can conflict with `pip`'s own vendored copy of `truststore` during large dependency resolutions (a `RecursionError` deep in SSL handling) — if that happens, temporarily rename `sitecustomize.py` for the duration of the `pip install`, then restore it.

## Run it

```bash
python main.py
```

`config.json` and `chats.json` will be created automatically on first run (see [Configuration](../configuration.md)).

## Project structure

```
test/
├── main.py           # Tkinter UI, chat networking, summarization
├── meeting.py         # Audio recording + transcription (no UI dependency)
├── theme.py            # Color palette + ttk.Style setup
├── installer.py         # Standalone installer GUI (built separately)
├── app_icon.ico          # App icon, used for both the exe and window icon
├── mkdocs.yml              # This documentation site's configuration
└── docs/                    # This documentation site's content
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
