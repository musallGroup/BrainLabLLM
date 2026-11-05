# aichat with streamed reasoning (patched build)

The upstream [aichat plugin](https://github.com/cosmocode/dokuwiki-plugin-aichat) sends a question
and waits for the complete answer: the person asking sees a progress bar, nothing else, and with a
reasoning model on a local GPU that can take half a minute. This patch makes the chat show the
model's reasoning live in a "Thinking…" block, then the answer while it is written, then the
finished answer with its sources (the reasoning stays available, collapsed, above it).

`streaming.patch` applies to upstream commit `dd5f504` (plugin date 2026-08-27). `build.sh`
downloads exactly that commit, applies the patch and writes `aichat-streaming.tar.gz`.

## What the patch changes

| File | Change |
|---|---|
| `Model/StreamingChatInterface.php` (new) | Interface for chat models that can stream |
| `Model/Ollama/ChatModel.php` | `streamAnswer()`: reads Ollama's NDJSON stream (`stream: true`, `think: true`) with cURL; falls back to no reasoning if the model has none. `getAnswer()` is unchanged and still used for rephrasing follow-up questions and by the CLI |
| `helper.php` | `askChatQuestion()` / `askQuestion()` take an optional callback for the pieces |
| `action.php` | With `stream=1` (and the setting on) the reply is NDJSON: `thinking` and `answer` pieces, then one `done` line with the usual `question`, `answer` (HTML), `sources`. Turns off every output buffer, gzip included, so each line leaves at once |
| `script/AIChatChat.js` | Reads the stream, fills the "Thinking…" block and the answer live. The chat history now keeps the model's own Markdown for the next question; upstream sent the rendered HTML back to the model as its previous turn |
| `conf/`, `lang/`, `syntax/chat.php` | Setting `streamThinking` (on by default; off = upstream behaviour), German and English labels |

Other chat models (OpenAI, Anthropic, ...) are unaffected: they answer without streaming as before.

## Build and install

```bash
./build.sh
```

Then in the wiki: **Admin → Extension Manager → Manual Install**, upload `aichat-streaming.tar.gz`.
It installs as `aichat` and replaces an installed upstream aichat; settings and the index stay.

> **Do not update aichat through the Extension Manager.** That installs upstream's version and
> removes the streaming. Upstream updates go through `build.sh` (below).

The web server must pass the reply on line by line. See [README.md](../README.md#36-streaming-through-the-web-server)
one folder up for nginx, Apache and PHP settings and a test.

## Moving to a newer upstream version

1. Clone upstream, check out the new commit, and apply the patch: `git apply --3way path/to/streaming.patch`.
2. Fix any conflicts, test (CLI `ask`, the chat in a browser, `streamThinking` off), commit.
3. Export: `git diff <new commit> HEAD > streaming.patch`, set `COMMIT` in `build.sh`, run it.

## Tested

On DokuWiki 2026-07-14c "Mort", PHP 8.3, with `qwen3.5:9b-mtp-q4_K_M` and `bge-m3` through the
gate (Ollama on an RTX 5090): reasoning appeared after about 0.7 s, the answer after 3-10 s.
The web server tested was PHP's built-in one, with DokuWiki's `gzip_output` on and off.
Follow-up questions, reloading the page (the chat is restored) and `streamThinking` off also worked.
Not tested: nginx or Apache in front, and models other than Ollama's.
