# Meetings

The Meeting tab records audio, transcribes it, and can turn the transcript into structured notes — all without needing to remember to take notes yourself.

## Choosing a microphone

The **Microphone** dropdown lists every input device Windows can see. Your last choice is remembered between sessions.

Click **Test Microphone** any time to record 2.5 seconds and get a plain-language result: either confirmation that sound was detected (with an approximate signal level), or a warning if nothing came through — with the most likely causes listed (wrong device selected, muted, or you didn't speak during the test). This exists because a muted microphone otherwise fails *silently*: recording appears to work, but the transcript comes back empty with no error message.

## Recording

Click **● Record**. The button turns red and becomes **⏹ Stop**, and a timer starts counting. Talk normally — there's no need to pause between sentences or speak unnaturally slowly.

Click **⏹ Stop** when you're done. The status area shows progress: *Stopping...* → *Transcribing...* → *Done*, and the full transcript appears in the Transcript panel once processing finishes.

## Transcribing an existing recording

Already have an audio or video file — a recording from a phone, a webinar download, a call recorded elsewhere? Click **📁 Transcribe File...** instead of Record, and pick the file. It runs through the exact same transcription (and afterward, summarization) pipeline as a live recording; the only difference is the audio comes from a file instead of a microphone. Most common formats work (wav, mp3, m4a, flac, ogg, and others) — anything the file dialog doesn't recognize can still be selected via "All files".

Recording and file transcription can't run at the same time — both buttons disable while either one is working, so there's no risk of them fighting over the same transcript.

### Why no live transcript? { #why-no-live-transcript }

An earlier version of this app showed the transcript incrementally while recording, using a voice-activity detector to chop speech into utterances as you talked. In testing, this broke down noticeably for fast or continuous speech: natural micro-pauses (a breath, a brief hesitation) were often mistaken for sentence breaks, fragmenting continuous thoughts mid-sentence and occasionally producing short, out-of-context clips that the speech model would fill in with plausible-sounding but wrong text.

Recording the whole thing and transcribing it in one pass — using the speech model's own, more sophisticated internal segmentation — turned out to be dramatically more reliable, at the cost of not seeing text appear while you talk. For meeting notes, accuracy matters more than a live readout, so that's the trade-off this app makes. See [Architecture](../architecture.md#why-batch-transcription) for the full story.

## Summarizing

Once a transcript is ready, click **✨ Summarize**. This produces structured notes with three sections:

- **Key Points** — what was actually discussed
- **Decisions** — anything the group agreed on
- **Action Items** — who's doing what

For short meetings, this is a single request to the AI server. For long meetings, the transcript is automatically split into chunks, each summarized independently, and then combined into one final set of notes — this keeps arbitrarily long meetings from exceeding the model's context window, and means a single garbled section can't corrupt the whole summary. See [Architecture](../architecture.md#summarization) for details.

You can click **Summarize** again at any time to regenerate the notes (for example, after switching AI server settings).

## Saving and exporting

- **💾 Save to chat history** adds the transcript and summary to the sidebar as a new entry, titled with the date and time, so you can find it later alongside your regular chats.
- **📤 Export .txt** saves the transcript and summary as a plain text file anywhere you choose — useful for emailing to people who weren't in the room, or archiving outside the app.

## Reading the status indicators

- The **timer** shows elapsed recording time.
- **Whisper: GPU** or **Whisper: CPU**, shown once the first transcription starts, tells you which one is doing the work. GPU is used automatically when available; this is purely informational.
- The status text on the right of the toolbar reflects what's currently happening (*Loading model...*, *Recording*, *Transcribing...*, *Summarizing part 2/5...*, *Done*, or an error message if something went wrong).
