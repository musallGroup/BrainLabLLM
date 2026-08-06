---
title: Home
---

# BrainLabLLM

A desktop app that gives your lab a private AI chat and meeting-notes assistant — running entirely on lab hardware, with no cloud services involved.

<div class="grid cards" markdown>

-   :material-chat-processing-outline:{ .lg .middle } **AI Chat**

    ---

    Chat with your lab's local language model. Attach code or text files for context, regenerate replies, copy responses, and keep a searchable history.

-   :material-microphone-outline:{ .lg .middle } **Meeting Transcription**

    ---

    Record a meeting, get a full transcript from a locally-run speech-to-text model — no audio ever leaves your machine.

-   :material-file-document-edit-outline:{ .lg .middle } **AI Summaries**

    ---

    Turn any transcript into structured notes — Key Points, Decisions, Action Items — with one click, even for hour-long meetings.

-   :material-book-search-outline:{ .lg .middle } **Wiki & Web Lookup**

    ---

    Opt-in, per-message tools that let the assistant fetch a page from the lab's internal wiki or search the public web to answer a specific question — both staying on the lab network.

-   :material-robot-outline:{ .lg .middle } **AI Coding Agent**

    ---

    An approval-gated assistant that can read, edit, and run commands in a project folder on your machine — every change is shown to you before it happens.

-   :material-download-box-outline:{ .lg .middle } **Zero-Friction Install**

    ---

    A double-click installer. No Python, no command line, no accounts. Speech recognition works fully offline out of the box.

</div>

## Why this exists

Cloud AI assistants are convenient, but sending meeting audio or proprietary code to a third-party service isn't always an option. This tool runs the two AI workloads it needs — speech-to-text and language generation — on infrastructure your lab already controls:

- **Speech-to-text** runs locally on *your own machine*, via a bundled [faster-whisper](https://github.com/SYSTRAN/faster-whisper) model. It works with no network connection at all.
- **Chat and summarization** talk to a language model running on a shared lab server over your local network — nothing leaves the building.

## What it looks like

The app has three tabs:

**Chat** — a familiar chat interface with a conversation sidebar, markdown-formatted replies (including syntax-highlighted code blocks), file attachments, and opt-in wiki lookup / web search per message.

**Meeting** — pick a microphone, hit Record, talk. When you stop, the full recording is transcribed in one pass and shown in a transcript panel. From there, a Summarize button produces structured notes, and you can export or save the result.

**Agent** — point it at a project folder and ask for a code change; it proposes edits and commands, and nothing runs until you approve it.

## Requirements

| | |
|---|---|
| **OS** | Windows 10 or 11 |
| **Network** | Lab network access, for chat and summarization only |
| **GPU** | Optional — speeds up transcription significantly, but the app runs fine on CPU |
| **Disk space** | ~2 GB (includes the bundled speech model) |
| **Technical skill** | None — see [Installation](getting-started/installation.md) |

## Get started

<div class="grid cards" markdown>

-   [:material-download: **Install the app**](getting-started/installation.md)

    Download and run the installer — takes under a minute.

-   [:material-rocket-launch: **Quick start**](getting-started/quick-start.md)

    Your first chat and your first recorded meeting.

-   [:material-cog: **Configuration**](configuration.md)

    Point the app at a different AI server, or tune the speech model.

-   [:material-lifebuoy: **Troubleshooting**](troubleshooting.md)

    Fixes for the most common issues.

</div>
