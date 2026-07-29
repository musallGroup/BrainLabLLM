# Contributing

This is an internal lab tool, but it's built to be easy to extend. A few notes for anyone picking it up.

## Code conventions

- **No comments explaining *what* code does** — names should make that obvious. Comments are reserved for *why*, when it isn't otherwise obvious (a workaround for a specific bug, a non-obvious constraint, a design trade-off).
- **Threading pattern**: any operation that could block (network calls, model loading, transcription) runs on a `threading.Thread`, with results delivered back to the UI via `root.after(0, callback, ...)`. Never touch a Tkinter widget from a background thread directly.
- **Generation tokens**: when adding a new cancellable/restartable operation, follow the existing pattern (`generation_token` in `ChatApp`, `recording_token` / `meeting_summary_token`) — increment an integer when a new operation starts, capture it in the background thread, and check it still matches before applying results to the UI. See [Architecture](../architecture.md#concurrency-model).
- **Friendly errors**: user-facing error messages should go through `friendly_error_message()` in `main.py` rather than showing raw exception text, for anything that could plausibly happen to a non-technical user (network errors especially).

## Testing changes

`agent.py` has a real automated test suite under `tests/` (pytest) — path scoping, the read/write/edit/search/shell tools, diff computation, and `AgentSession`'s control flow (Planning vs. Auto mode, approve/reject, cancellation, the iteration cap, path-escape attempts). Run it with:

```bash
pip install pytest
pytest tests/
```

Most tests are fast and don't touch the network. A handful (`tests/test_agent_live.py`, the classes marked `@requires_lab_server`) exercise the real tool-calling loop against the lab Ollama server and are skipped automatically with a clear reason if that server isn't reachable — this is deliberate: `agent.py` is tkinter-free by design (see [Architecture](../architecture.md)), which is exactly what makes it practical to test this way, unlike the Tkinter UI layer below.

`main.py`, `meeting.py`, and the UI layer in general don't have an automated suite — the practical approach used throughout development instead:

- **`meeting.py` changes**: test with `python meeting.py` (the built-in console test) before touching the UI, to isolate audio/transcription bugs from UI bugs.
- **UI changes**: drive `ChatApp` methods directly from a throwaway script rather than clicking through manually — for example:

```python
import tkinter as tk
import main

root = tk.Tk()
app = main.ChatApp(root)
app._add_user_message("test")
app._render_history()
# ...assert on app.history.get("1.0", tk.END), widget states, etc.
root.destroy()
```

  This is dramatically faster to iterate on than manual clicking, and is how the layout/styling/threading bugs documented in [Architecture](../architecture.md) were actually found and fixed.

- **After any change touching `meeting.py` or the recording flow**: test with a *real* microphone and real speech before considering it done — silent failures (like the muted-mic issue documented in [Troubleshooting](../troubleshooting.md)) don't show up in code review or unit-style tests.
- **Before a release**: rebuild the full installer (see [Packaging](packaging.md)) and test the actual installed `.exe`, not just `python main.py` — packaging-specific bugs (missing DLLs, bundled model path resolution) only show up in the built artifact.

## Making changes to the documentation site

This site is built with [MkDocs](https://www.mkdocs.org/) and the [Material theme](https://squidfunk.github.io/mkdocs-material/). To preview changes locally:

```bash
pip install mkdocs-material mkdocs-mermaid2-plugin
mkdocs serve
```

Then open `http://127.0.0.1:8000`. Pushing to the repository's default branch deploys automatically via the GitHub Actions workflow in `.github/workflows/docs.yml`.

## Proposing changes

Open a pull request. For anything touching the recording/transcription pipeline or the packaging process, please describe what you tested it with (real mic + real speech, or the specific machine/GPU configuration) in the PR description — those are exactly the areas where changes that look correct in code review have historically failed in practice.
