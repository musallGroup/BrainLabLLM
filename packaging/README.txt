BrainLabLLM - Quick Start
==========================================

WHAT THIS IS
A desktop app for chatting with our lab's local AI model, and for
recording/transcribing/summarizing meetings - all running on lab hardware,
no cloud services involved.

INSTALL
1. Copy this whole folder (or the .zip) to your computer, anywhere you like.
2. Run "BrainLabLLMSetup.exe".
   NOTE: Windows will very likely show a blue "Windows protected your PC"
   screen the first time - this happens for any brand-new, unsigned program
   and does NOT mean anything is wrong. Click "More info", then
   "Run anyway". You'll only see this once.
3. Click "Install". A shortcut appears on your Desktop and in the Start Menu.
4. That's it - no other setup needed. Speech recognition runs entirely on
   your own machine and works fully offline; only the chat/summary features
   need the lab network.

USING IT
- Chat tab: type a message, press Enter to send.
- Meeting tab:
    1. Pick your microphone from the dropdown (click "Test Microphone" if
       you're not sure it's working).
    2. Click "Record", talk, click "Stop".
    3. Wait for the transcript to appear, then click "Summarize" for a
       structured summary, or "Export .txt" to save a copy.
    4. "Save to chat history" keeps it in the sidebar for later.

REQUIREMENTS
- You must be on the lab network (or VPN) for the chat/summary features -
  they talk to our shared AI server. Speech-to-text works without network.
- A GPU speeds up transcription but isn't required; it falls back to CPU
  automatically.

CHANGING SETTINGS
If the lab's AI server address ever changes, open the app, go to
File > Settings, and update the server address there (no file editing
needed). Use "Test Connection" to confirm it works before saving.

TROUBLESHOOTING
- "No sound detected" when testing the mic: check Windows Sound settings
  (right-click the speaker icon > Sound settings > Input) to make sure the
  right microphone is selected and not muted.
- Can't reach the AI server: make sure you're connected to the lab network.
- First recording after installing takes a few extra seconds while the
  speech model loads into memory - this is normal, later recordings are
  faster.
- Antivirus flags the installer or blocks it: this can happen with new,
  unsigned software. It's safe - if your antivirus quarantines it, restore
  it from quarantine or ask IT to allowlist it.
- If a machine has a graphics card but transcription always falls back to
  CPU (shown next to the Record button), the GPU may not be usable on that
  machine (outdated driver, etc.) - the app detects this automatically and
  uses CPU instead so it still works, just slower.
