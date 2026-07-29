# Agent

The Agent tab lets the same local model act as a coding assistant against a project folder on your machine — reading files, proposing edits, and (if you let it) running commands. Nothing it does is invisible: every change it wants to make is shown to you before it happens.

## Choosing a project folder

Click **Browse...** and pick the folder you want the agent to work in. It can only see and touch files inside that folder — anything outside it (including going "up" with `..` or giving an absolute path elsewhere on your machine) is refused automatically, even if the agent tries. Your last-used folder is remembered between sessions.

## Planning vs. Auto

Two modes, chosen with the radio buttons above the transcript:

- **Planning** — the agent can freely read files and search the project to understand it, but any change it wants to make is only ever shown to you as a proposed diff. **Nothing is written to disk in this mode.** Use this to see what the agent would do before committing to anything.
- **Auto** — the agent can actually make changes and run commands, but it stops and asks before every single one. You'll see the exact diff (for a file edit) or the exact command (for a shell command) and have to click **Approve** or **Reject** before it proceeds. There's no "run everything unattended" option — this is deliberate.

If you reject a proposed change, the agent is told you declined it and adapts — it won't just try the identical change again.

## Working with it

Describe what you want in the input box and press Enter (or **Send**). The transcript shows the agent's reasoning as it happens:

- 📄 / 📁 / 🔍 icons mark it reading a file, listing a folder, or searching code — these never need approval, since they can't change anything.
- ✏️ marks a proposed file edit — shown as a diff, colored like a standard patch (green additions, red removals).
- 💻 marks a shell command — shown as the literal command that would run.

Click **⏹ Stop** at any time to cancel a run in progress. If it was mid-way through waiting for your approval on something, stopping cancels that too — nothing gets applied.

## What it can and can't do

- It can read and search any file in the project folder, and propose creating, overwriting, or making a targeted edit to a file.
- In Auto mode, it can also run shell commands (like `pip install` or `pytest`) inside the project folder — always shown to you first, always requiring approval.
- It cannot see or touch anything outside the project folder you picked, no matter what it's asked to do.
- Agent conversations aren't saved to your chat history the way regular chats are — they're scoped to the current session. Start a new conversation with the agent by picking a folder and sending a new instruction.

## Why it's built this way { #why-approval-gated }

See [Architecture](../architecture.md#agent-tool-calling) for the reasoning behind approval-gating every change rather than letting the agent run fully unattended.
