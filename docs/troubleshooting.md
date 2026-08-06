# Troubleshooting

## Installation

### "Windows protected your PC"

This is expected for any brand-new, unsigned program — it's a reputation check (SmartScreen), not a malware detection. Click **More info**, then **Run anyway**. It only appears once.

### Antivirus flags or quarantines the installer

Also common for new, unsigned software. If your antivirus quarantines it, restore it from quarantine, or ask IT to allowlist it. If you'd like independent confirmation it's clean, you can scan it yourself with Windows Defender or upload the file to a service like VirusTotal.

### "Setup files missing" when running the installer

The installer (`BrainLabLLMSetup.exe`) needs the `BrainLabLLM` folder sitting in the same directory as itself. If you moved or renamed just the `.exe`, re-extract the original `.zip` and run it from there without moving anything first.

## Microphone and recording

### The transcript comes back empty every time

This is almost always a muted or wrong microphone — recording silently "succeeds" even with no audio, so there's no error to see. Go to the Meeting tab and click **Test Microphone**:

- If it reports **no sound detected**, check:
    1. The correct device is selected in the dropdown (a webcam mic and a headset mic can both show up — make sure you picked the one that's actually connected/in use)
    2. Windows Sound settings → **Recording** tab → confirm the device isn't muted and its level isn't at 0
    3. You were actually speaking during the 2.5-second test

### My microphone doesn't appear in the dropdown

Click into the Meeting tab again to refresh the device list (it's read fresh from Windows each time the app builds that screen). If it's a USB device, try unplugging and replugging it, and confirm Windows itself sees it (Settings → System → Sound).

### Fast or continuous speech produces garbled or fragmented text

This should no longer happen — an earlier design that transcribed live while recording had exactly this problem, which is why the app now transcribes the whole recording in one pass after you stop. See [Architecture](architecture.md#why-batch-transcription) for why. If you're still seeing fragmented results, please report it — this would be a regression.

### Transcription always uses CPU, never GPU, even though this machine has a graphics card

The app tries the GPU automatically and falls back to CPU if it can't be used (outdated driver, unsupported card, or a hung/broken CUDA setup). This is intentional — CPU is slower but always works, so the app prefers "slow but working" over "fast but crashes." If you want to confirm what's going wrong, an administrator can set `"whisper_device": "cuda"` in `config.json` (see [Configuration](configuration.md#whisper_device)) to force GPU use and see the actual error instead of silently falling back.

## Chat and AI features

### "Can't reach the AI server"

You're most likely not connected to the lab network. Connect via VPN or on-site, then try again. Use **File → Settings → Test Connection** to confirm.

### The AI server address changed and now nothing works

Open **File → Settings**, update the **Server address**, click **Test Connection** to confirm it works, then **Save** and restart the app. See [Settings](user-guide/settings.md).

### Web Search says it can't reach the search service

Web search runs through a separate service on the lab network, independent of the AI server itself — being connected to the lab network for normal chat doesn't guarantee this service is also reachable. If regular chat and wiki lookup work fine but web search specifically doesn't, this is most likely that service being down or not reachable from your machine; report it to whoever manages this tool for your lab rather than assuming it's something you can fix from Settings.

### A file I tried to attach was rejected

Only text-based files are supported (source code, `.txt`, `.md`, config files, logs, etc.) — the AI model reads text, not images or binary formats like `.pdf` or `.docx`. Very large files (over roughly 200 KB) are truncated rather than rejected outright; a truncated attachment is marked as such.

## General

### The app won't start at all

Check Task Manager for a lingering `BrainLabLLM.exe` process from a previous crash and end it, then try launching again. If that doesn't help, try reinstalling — running the setup installer again is safe and will overwrite the existing install.

### I want to see my old chat history but reinstalled the app

Chat history lives in `%APPDATA%\BrainLabLLM\chats.json`, separate from the app's install folder, so a normal reinstall (installing over the same location) doesn't touch it. If you're moving to a **new machine**, copy that file across manually.

### Still stuck?

Check the [Configuration](configuration.md) reference in case a setting is misconfigured, or reach out to whoever manages this tool for your lab.
