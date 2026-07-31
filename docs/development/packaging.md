# Packaging & Distribution

How the app becomes the `.zip` package end users download — including several non-obvious gotchas that cost real debugging time, documented here so they don't have to be rediscovered.

## Design goals

1. **Zero coding experience required to install or run it.**
2. **Fully offline speech-to-text** — no lab machine should need internet access just to transcribe a meeting.
3. **No new software required on the build machine beyond what's already needed to develop the app** — deliberately avoided pulling in a separate installer-building tool (see [why](#why-not-inno-setup)).

## Building the app bundle

The app is packaged with [PyInstaller](https://pyinstaller.org) in `--onedir` mode (not `--onefile`) — with ~6 GB of bundled model weights and DLLs (most of it PyTorch's CUDA runtime, needed for [speaker identification](#diarization-model-bundling)), `--onefile`'s startup-time self-extraction to a temp directory would add meaningful launch latency on every run; `--onedir` pays that cost once, at install time, instead.

```bash title="Build command (run from the project root)"
pyinstaller --name BrainLabLLM --onedir --windowed --noconfirm --noupx \
  --icon app_icon.ico \
  --add-data "<path-to-cached-whisper-medium-model>;whisper_model" \
  --add-data "<path-to-cached-pyannote-diarization-model>;diarization_model" \
  --add-binary "<conda-env>\Library\bin\tcl86t.dll;." \
  --add-binary "<conda-env>\Library\bin\tk86t.dll;." \
  --add-binary "<conda-env>\Library\bin\liblzma.dll;." \
  --add-binary "<conda-env>\Library\bin\libbz2.dll;." \
  --add-binary "<conda-env>\Library\bin\ffi.dll;." \
  --add-binary "<conda-env>\Library\bin\ffi-7.dll;." \
  --add-binary "<conda-env>\Library\bin\ffi-8.dll;." \
  --add-binary "<conda-env>\Library\bin\libexpat.dll;." \
  --collect-all ctranslate2 \
  --collect-all faster_whisper \
  --collect-all onnxruntime \
  --collect-all tokenizers \
  --collect-all huggingface_hub \
  --collect-all torch \
  --collect-all torchaudio \
  --collect-all torchcodec \
  --collect-all pyannote.audio \
  --collect-all pyannote.core \
  --collect-all pyannote.database \
  --collect-all pyannote.pipeline \
  --collect-all pyannote.metrics \
  --collect-all pyannoteai_sdk \
  --collect-all asteroid_filterbanks \
  main.py
```

!!! note "`--noupx`: don't compress the CUDA DLLs"
    UPX compression is skipped for this build. `torch`'s bundled CUDA runtime (`cublas`, `cudnn`, `cusparse`, `cufft`, `cusolver`) is already ~4 GB of dense binary — compressing it buys little, adds real time to every build, and UPX has a history of flaky interaction with large, complex DLLs. Simpler to just not risk it for marginal savings.

### Why the explicit `--add-binary` DLLs { #dll-gotcha }

PyInstaller's automatic dependency scanner, when run from a **conda** environment on Windows, does not reliably find `tcl86t.dll` / `tk86t.dll` (needed for Tkinter itself) or a handful of other C-extension dependencies (`liblzma`, `libbz2`, `ffi`, `libexpat`) — they live in `<conda-env>\Library\bin\`, a location PyInstaller's scanner doesn't check by default when building from a conda Python, as opposed to a "vanilla" python.org install where these ship alongside the interpreter itself.

**Symptom if you skip this**: the built `.exe` fails immediately with `ImportError: DLL load failed while importing _tkinter` (or `_ctypes`, depending on which DLL is missing), even though the exact same code runs fine with `python main.py` in the dev environment. The build log itself gives a hint — look for `WARNING: Library not found: could not resolve '...'` lines.

### Bundling the speech model for offline use { #model-bundling }

`faster-whisper` normally downloads model weights from Hugging Face Hub on first use and caches them locally. To avoid every lab machine needing internet access (and to avoid a slow first-run download on a shared/proxied network), the model's cache directory is bundled directly into the app via `--add-data`, and `meeting.py`'s `resolve_model_path()` checks `sys.frozen` to decide whether to load from the bundled local path or fall back to the Hugging Face model name (dev mode only):

```python
def resolve_model_path(model_size):
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "whisper_model")
        if os.path.isdir(bundled):
            return bundled
    return model_size
```

`faster-whisper`'s `WhisperModel(...)` constructor accepts either a Hugging Face model name *or* a local directory path containing the converted model files (`model.bin`, `config.json`, `tokenizer.json`, `vocabulary.txt`) — this is what makes the swap possible without touching the loading code itself.

### Bundling the speaker-identification model { #diarization-model-bundling }

The same pattern is reused for `pyannote/speaker-diarization-community-1` (see [Architecture](../architecture.md#speaker-diarization) for why this model specifically): its cache directory is bundled via `--add-data ...;diarization_model`, and `diarization.py`'s `resolve_diarization_model_path()` checks `sys.frozen` the same way `resolve_model_path()` does, falling back to the Hugging Face repo id plus a dev-only `HUGGINGFACE_TOKEN` (see [Building from Source](building.md)) when running unfrozen. `pyannote.audio`'s `Pipeline.from_pretrained(...)` accepts a bare local directory path with no token needed, exactly like `WhisperModel` does — confirmed directly, since this is the one part of the frozen build that's easy to get subtly wrong without testing it.

This is a much heavier addition than the speech model: `torch`'s CUDA runtime alone is roughly 4 GB (`cublas`, `cudnn`, `cusparse`, `cufft`, `cusolver` — the actual math libraries GPU tensor ops need, not something safely prunable). That's a deliberate, discussed trade-off, not an oversight — see [Installation](../getting-started/installation.md) for the resulting download size end users see. The alternative (a separate, optional "with Speaker ID" build) was considered and rejected in favor of keeping a single installer simple to build, test, and hand out, at the cost of every install carrying weight that machines without a GPU can never use.

## GPU/CPU robustness across unknown hardware

Lab machines vary — some have a capable GPU, some don't, some have one with an outdated driver. `MeetingSession._ensure_model_loaded()` handles this in two layers:

1. **A try/except around GPU model construction and a warmup transcription call**, falling back to CPU on any exception.
2. **A timeout**, not just an exception handler: GPU initialization runs on its own thread and is joined with a timeout. A plain try/except can't catch a *hang* — and a genuinely broken driver/CUDA combination can hang rather than raise a clean error. If GPU init doesn't complete within 30 seconds, the app proceeds on CPU regardless, leaving the stuck thread to die on its own in the background (it's a daemon thread).

`config.json`'s `whisper_device` setting (`auto` / `cuda` / `cpu`) lets an administrator override this behavior per-machine if needed — see [Configuration](../configuration.md#whisper_device).

## The installer

Rather than a separate installer-building tool, `installer.py` is a small, dependency-free Tkinter GUI, built with PyInstaller the same way as the main app (`--onefile`, since it has no heavy dependencies of its own). It still uses Tkinter, so it needs the same [conda-env DLL fix](#dll-gotcha) as the main app — skipping it produces an installer that crashes immediately with `DLL load failed while importing _tkinter`:

```bash
pyinstaller --name BrainLabLLMSetup --onefile --windowed --noconfirm \
  --icon app_icon.ico \
  --add-binary "<conda-env>\Library\bin\tcl86t.dll;." \
  --add-binary "<conda-env>\Library\bin\tk86t.dll;." \
  --add-binary "<conda-env>\Library\bin\liblzma.dll;." \
  --add-binary "<conda-env>\Library\bin\libbz2.dll;." \
  --add-binary "<conda-env>\Library\bin\ffi.dll;." \
  --add-binary "<conda-env>\Library\bin\ffi-7.dll;." \
  --add-binary "<conda-env>\Library\bin\ffi-8.dll;." \
  --add-binary "<conda-env>\Library\bin\libexpat.dll;." \
  installer.py
```

It expects the built `BrainLabLLM` folder to sit next to it, copies it to `%LOCALAPPDATA%\Programs\BrainLabLLM\` (a per-user location — no administrator rights needed), and creates Desktop and Start Menu shortcuts via a small PowerShell `WScript.Shell` COM call (no extra Python packages required for that either).

### Why not Inno Setup or a similar tool { #why-not-inno-setup }

A more conventional approach would use a dedicated installer-authoring tool. That was deliberately avoided here: it would require downloading and installing new third-party software onto the build machine, which is a meaningfully different kind of action than installing a Python package via `pip` for development purposes, and isn't something to do without an explicit go-ahead. A minimal hand-rolled installer using only what's already needed to build the app (PyInstaller, Tkinter) sidesteps that entirely while still producing a normal-feeling double-click installer experience.

## Assembling the distributable

The plain-language end-user `README.txt` is tracked in source at `packaging/README.txt` (the `dist/` folder itself is gitignored, so anything only living there is lost on a clean rebuild) — copy it in before zipping:

```bash
Copy-Item 'packaging\README.txt' 'dist\README.txt' -Force
Compress-Archive -Path 'dist\BrainLabLLM', 'dist\BrainLabLLMSetup.exe', 'dist\README.txt' `
  -DestinationPath 'dist\BrainLabLLM_Setup_Package.zip' -Force
```

The result — `BrainLabLLMSetup.exe` sitting next to the `BrainLabLLM` folder, plus the plain-language `README.txt` — is what gets shared with lab members. See [Installation](../getting-started/installation.md) for the end-user side of this.

## Expect Windows SmartScreen and antivirus warnings

Because the resulting `.exe` files aren't code-signed, Windows SmartScreen will show a "protected your PC" warning on first run on *any* machine — this is a reputation check based on how many times a given file hash has been seen, not a malware verdict, and is unavoidable without a paid code-signing certificate. Similarly, some antivirus products flag new, unsigned, PyInstaller-built executables heuristically. Neither indicates an actual problem; both are documented for end users in [Troubleshooting](../troubleshooting.md#installation).
