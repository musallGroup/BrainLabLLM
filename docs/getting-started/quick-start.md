# Quick Start

Two things to try first: a chat message, and a recorded meeting.

## Your first chat message

1. Open **BrainLabLLM** from your Desktop or Start Menu.
2. You'll land on the **Chat** tab.
3. Type a message in the box at the bottom and press ++enter++ (use ++shift+enter++ for a new line without sending).
4. The reply streams in as it's generated.

That's the whole workflow. A few things worth knowing:

- **New chat** (top of the sidebar) starts a fresh conversation. Old conversations stay in the sidebar — click any of them to go back.
- The 📎 button next to the input box lets you [attach a file](../user-guide/chat.md#attaching-files) (code, logs, notes) so the model can see its contents.
- If a reply is taking a while, the **Send** button becomes **Stop** — click it to cancel.

## Your first recorded meeting

1. Switch to the **Meeting** tab.
2. Check the **Microphone** dropdown is set to the right device. If you're not sure, click **Test Microphone** and say something — it'll tell you plainly whether it picked up sound.
3. Click **● Record**, then talk normally. There's no live transcript while recording — that's intentional (see [why](../user-guide/meetings.md#why-no-live-transcript)).
4. Click **⏹ Stop** when you're done. The whole recording gets transcribed in one pass, which takes a few seconds for a short meeting.
5. Once the transcript appears, click **✨ Summarize** for structured notes (Key Points / Decisions / Action Items).
6. Use **💾 Save to chat history** to keep it in the sidebar, or **📤 Export .txt** to save it as a plain text file you can share.

!!! tip "First recording is a little slower"
    The speech-to-text model loads into memory the first time you record after opening the app — you'll see "Loading model..." for a few seconds. Every recording after that is faster.

## Next steps

- [Chat features in depth](../user-guide/chat.md)
- [Meeting features in depth](../user-guide/meetings.md)
- [Change the AI server address](../user-guide/settings.md)
