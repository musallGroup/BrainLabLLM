# Chat

The Chat tab is a straightforward conversation interface with a few features aimed at coding and technical work.

## Sending messages

Type in the input box and press ++enter++ to send. ++shift+enter++ inserts a line break instead of sending, for multi-line messages.

While the model is replying, the send button becomes a **Stop** button — click it to cancel generation early. Whatever was generated so far is kept in the conversation, marked `[stopped]`.

## Managing conversations

The sidebar lists every conversation you've had, most recent first.

- **+ New chat** starts a fresh conversation. A conversation's title is set automatically from your first message (or the first attached file's name, if you send an attachment with no text).
- Click any item in the sidebar to switch to it.
- **🗑 Delete chat** removes the current conversation after a confirmation prompt.

Conversations are saved automatically after every message — there's no explicit save action, and nothing is lost if the app closes unexpectedly.

## Markdown and code formatting

Replies are rendered with lightweight markdown support:

- `**bold**` renders as **bold**
- `` `inline code` `` renders in a monospace font
- Triple-backtick fenced code blocks render as a distinct, syntax-highlight-style dark block

This means code the model writes is easy to read and copy directly from the chat.

## Regenerate and copy

- **↻ Regenerate** discards the last reply and asks the model to try again — useful if a response wasn't quite right. Only available when the last message is from the assistant.
- **📋 Copy last reply** copies the most recent assistant response to your clipboard.

## Attaching files

Click the **📎** button next to the input box to attach one or more files to your next message. This lets you ask questions about a specific piece of code, a log file, or notes without pasting them in by hand.

**What you can attach:** any text-based file — source code, `.txt`, `.md`, `.json`, `.csv`, log files, configuration files, and similar. The content is read as plain text and included directly in your message, wrapped in a code block so it's clearly separated from your own text.

**What you can't attach:** binary files (images, PDFs, Word documents, executables, etc.) — the model this app talks to reads text only, so these are rejected with a message explaining why.

**Size limit:** each file is capped at roughly 200 KB. Larger files are truncated (and marked "truncated" on the attachment chip) so a single huge file can't push the whole conversation past the model's context window.

Once you attach a file, it appears as a small chip above the input box showing its name — click the **✕** on a chip to remove it before sending. Attachments are cleared automatically after you send.

!!! tip "Multiple files at once"
    The file picker supports selecting multiple files in one go — hold ++ctrl++ (or ++shift++ for a range) while selecting in the dialog.
