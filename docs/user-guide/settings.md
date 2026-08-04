# Settings

Most day-to-day settings live in **File → Settings**, no file editing required. (Some lower-level settings are file-based — see [Configuration](../configuration.md) for those.)

## AI Server Settings

Open **File → Settings** (or press ++ctrl+comma++) to open the dialog.

| Field | What it does |
|---|---|
| **Server address** | The URL of your lab's Ollama server's chat endpoint, e.g. `http://10.3.2.112:11434/api/chat`. Change this if your lab's AI server moves to a new address. |
| **Model name** | The name of the model to use on that server, e.g. `qwen3.6:35b-coder`. Change this to switch models if your lab runs more than one. |

Click **Test Connection** before saving to confirm the app can actually reach the server and get a response — this catches typos and network issues immediately rather than after you close the dialog.

Click **Save**, then restart the app for the new settings to take effect.

!!! note "Why a restart?"
    Keeping configuration as a simple, restart-to-apply setting avoids a class of bugs where half the app is using old settings and half is using new ones mid-session — deliberately simple over deliberately clever.

## Dark mode

**View → Dark Mode** switches the whole app's color theme instantly — no restart needed. Your choice is remembered for next time.

## What's not in this dialog

The speech-to-text model size and whether it prefers GPU or CPU are set via the `config.json` file instead, since they're the kind of setting an administrator sets up once per machine rather than something an individual user changes day to day. See [Configuration](../configuration.md).
