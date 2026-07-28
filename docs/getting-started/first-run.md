# First-Time Setup

Most users don't need to change anything — the app ships pre-configured to talk to your lab's AI server. This page covers what actually happens behind the scenes on first launch, and the handful of things worth checking.

## What happens on first launch

1. A `config.json` file is created next to the installed app (if one doesn't already exist), containing the default server address, model name, and speech settings. See [Configuration](../configuration.md) for the full reference.
2. A per-user data folder is created at `%APPDATA%\BrainLabLLM\` for your chat history and preferences — kept separate from the install location so it survives reinstalls and works even though the app itself is installed somewhere you might not have write access to.
3. On the Meeting tab, the app picks a default microphone automatically. Your device names are populated live from Windows — nothing needs to be pre-configured.

## Check your microphone once

Before your first real meeting, switch to the **Meeting** tab and click **Test Microphone**. This catches the single most common first-run problem: a muted or wrong microphone, which otherwise fails silently (recording "succeeds" but the transcript comes back empty, with no error).

## Confirm you can reach the AI server

Open **File → Settings** and click **Test Connection**. If it fails, you're most likely not on the lab network — connect via VPN or on-site and try again. This doesn't affect the Meeting tab's transcription, which works fully offline.

## GPU or CPU?

If your machine has a supported NVIDIA GPU, the app uses it automatically for much faster transcription (a few seconds instead of tens of seconds for a short recording). This is fully automatic — after your first recording completes, look for the **Whisper: GPU** or **Whisper: CPU** label next to the Record button to see which one was used. There's nothing to configure unless you want to force one or the other; see [Configuration](../configuration.md#whisper_device).
