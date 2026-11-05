# AI search for a DokuWiki (aichat + local models)

This sets up a GPU machine that answers questions about a DokuWiki's content, through the
[aichat plugin](https://www.dokuwiki.org/plugin:aichat), with models that run on that machine.
Nothing leaves the local network except model downloads. People use it from a chat button in
the wiki; the answers come from the wiki pages, with links to the pages they came from.

It is separate from the rest of this repository (no Webex bot, reminders, Open WebUI or web
search) and shares nothing with it.

```
 browser ──> DokuWiki web server ──────────────> AI machine (this setup)
             aichat plugin (patched)   :11435    aichat-gate ──> Ollama (127.0.0.1:11434)
             index of the wiki (SQLite)  token    caps context    qwen3.5:9b-mtp  (answers)
                                                  sets reasoning  bge-m3          (search index)
```

| Part | Where | What it does |
|---|---|---|
| **aichat** (patched build) | wiki server | Splits the wiki into chunks, has them turned into vectors (the search index), finds the chunks that match a question and lets the model answer from them. The patch streams the model's reasoning and the answer into the chat as they are written ([dokuwiki-plugin/](dokuwiki-plugin/README.md)) |
| **Ollama** | AI machine | Runs the two models; listens on localhost only |
| **aichat-gate** | AI machine | The only port the wiki server reaches. It checks a token, passes on only what the plugin needs, and adjusts two things the plugin gets wrong for local models (below) |
| `qwen3.5:9b-mtp-q4_K_M` | AI machine | Writes the answers. The `-mtp` build uses multi-token prediction: it guesses several tokens ahead and checks them in one step, which makes writing faster |
| `bge-m3` | AI machine | Turns text into vectors for the search, in German, English and many other languages |

Why the gate: for a local model, aichat sends the model's full trained context (up to 256k
tokens) with every request, which does not fit next to the model in 16 GB; and it never says
whether the model should reason, so a reasoning model reasons before every answer, also for the
small internal step that rephrases follow-up questions. The gate caps the context at 32k tokens
and turns reasoning off unless the request asks for it (the patched plugin asks only for the
answer it streams). Ollama itself has no passwords; the gate's token keeps everyone except the
wiki server off the GPU.

> **Status:** tested so far:
> - the gate, the self-test, the patched plugin and the model choice, against a real Ollama (on
>   an RTX 5090) and a test DokuWiki;
> - the service unit, with all its restrictions, under real systemd;
> - `install.sh` in 21 dry-run scenarios, with every system change faked: fresh install, re-run,
>   update, missing driver, driver waiting for a reboot, old Ollama, other SSH port, too little
>   disk space, bad arguments.
>
> It has not yet run for real on a clean Ubuntu machine with the RTX 5070 Ti, so keep its output
> the first time.

## 1. What you need

**The machine** (the one this was planned for): ASUS PRIME B760-PLUS, Intel Core i7-14700K,
32 GB DDR5, Samsung 9100 PRO 1 TB, RTX 5070 Ti 16 GB. Any NVIDIA GPU with 16 GB or more works.

**From IT:**

- **BIOS update first**, before long runs: Intel 13th/14th-generation CPUs had an instability
  that a microcode update in the BIOS fixes.
- Ubuntu 24.04 LTS with OpenSSH, and an account with `sudo` (not root) for the installer.
- A fixed IP address (or DHCP reservation), ideally a DNS name.
- Outbound internet: apt mirrors, `ollama.com` and its model registry, `github.com`.
- Inbound: port **11435** from the wiki server only (the installer sets up the firewall for it),
  SSH for administration.
- The wiki server's IP address.

**On the wiki server:** DokuWiki 2026-07-14 "Mort" or newer, PHP 8.1 or newer with the
`pdo_sqlite` and `curl` extensions, shell access for the index job and a scheduler (cron).

## 2. Install the AI machine

```bash
sudo apt-get install -y git
git clone https://github.com/musallGroup/BrainLabLLM
cd BrainLabLLM/server/aichat
./install.sh --wiki-server 192.168.1.20
```

Use the wiki server's real address. Without an NVIDIA driver, the first run installs one and
asks you to **reboot and run the same command again**. With Secure Boot on, the driver install
may ask for a password, and a blue "Perform MOK management" screen appears after the reboot:
choose *Enroll MOK* and enter that password, or the driver will not load. The models are about
10 GB; the download is the slow part.

The installer ends with a self-test and prints the settings for the wiki, including the token.
Run the test again at any time:

```bash
./check.sh
```

Every line should say `OK`. It also measures decoding speed (see [Speed](#speed)).

| Option | Effect |
|---|---|
| `--wiki-server IP[,IP]` | The wiki server(s) allowed to reach the gate |
| `--no-firewall` | Leave the firewall to IT (then open 11435 for the wiki server yourself) |
| `--chat-model NAME` | Default `qwen3.5:9b-mtp-q4_K_M` |
| `--embed-model NAME` | Default `bge-m3` |
| `--context N` | Context cap in tokens, default 32768 |
| `--no-auto-reboot` | Automatic updates do not reboot the machine (see [Updates](#updates)) |
| `--update` | Only re-copy the gate from this checkout and restart it |

What it changes on the machine:
- **Ollama**, with a drop-in in `/etc/systemd/system/ollama.service.d/aichat.conf`.
- **The gate** in `/opt/aichat-gate/`, its settings and token in `/etc/aichat-gate.env` (root
  only), and the service `aichat-gate`.
- **ufw:** SSH on the port `sshd` uses, and 11435 only from the wiki server.
- **Automatic updates** reboot at 03:30 when an update needs it, via
  `/etc/apt/apt.conf.d/52aichat-auto-reboot` (see [Updates](#updates)).

## 3. Set up the wiki

### 3.1 Plugins

1. **Admin → Extension Manager**: search for and install the **sqlite** plugin.
2. Build the patched aichat on any machine with this repository (Linux, or Git Bash on Windows):
   ```bash
   server/aichat/dokuwiki-plugin/build.sh
   ```
3. **Admin → Extension Manager → Manual Install**: upload `aichat-streaming.tar.gz`.
   Never update aichat from the Extension Manager later; that removes the streaming
   ([dokuwiki-plugin/README.md](dokuwiki-plugin/README.md)).

### 3.2 Settings

**Admin → Configuration Manager → aichat.** The model fields offer a list but accept any text.

| Setting | Value |
|---|---|
| `chatmodel` | `Ollama qwen3.5:9b-mtp-q4_K_M` |
| `rephrasemodel` | `Ollama qwen3.5:9b-mtp-q4_K_M` |
| `embedmodel` | `Ollama bge-m3` |
| `storage` | `SQLite` |
| `ollama_apiurl` | `http://<AI machine>:11435/api` (note the `/api`) |
| `ollama_apikey` | the token the installer printed (`sudo grep TOKEN /etc/aichat-gate.env` on the AI machine) |
| `similarityThreshold` | `50` (the default 75 suits OpenAI's search model, not `bge-m3`; see [Tuning](#tuning)) |
| `customprompt` | `Reply in the language the user question is written in: an English question gets an English answer, a German question a German answer. Answer only from the documents above; if they do not contain the answer, say so. Format the answer in Markdown.` |
| `streamThinking` | on |
| `restrict` | who may use the chat, e.g. `@user` for logged-in users only; empty = everyone who can see the page |
| `skipRegex` | pages never to index; default `:(playground\|sandbox)(:\|$)`, add private namespaces here |
| `logging` | off, unless you want questions and answers in DokuWiki's log viewer (a privacy decision) |

Keep the other settings at their defaults (`contextChunks` 5, `chunkSize` 1500, `chatHistory` 1,
`rephraseHistory` 1). The answers are rendered as Markdown, which is what the custom prompt asks
for; ignore the hint on the plugin page to make local models write DokuWiki syntax.

The custom prompt matters: without it the plugin tells the model to fall back to the wiki's
language when unsure, and in tests the model then answered English questions in German.

### 3.3 Connection test

On the wiki server:

```bash
curl -s -H "Authorization: Bearer <token>" http://<AI machine>:11435/api/version
```

`{"version":"..."}` means the network, firewall and token are right. A timeout means the firewall;
`missing or wrong token` means the token.

### 3.4 Build the index

From the DokuWiki directory, as the web server's user (`www-data` on Debian/Ubuntu):

```bash
sudo -u www-data php bin/plugin.php aichat embed
sudo -u www-data php bin/plugin.php aichat info
sudo -u www-data php bin/plugin.php aichat ask "a question the wiki answers"
```

`info` shows how many chunks are indexed. If it is far fewer than the wiki has pages, DokuWiki's
own search index is behind: run `sudo -u www-data php bin/indexer.php` and `embed` again.

Then keep the index current every night (`sudo crontab -e -u www-data`):

```
0 2 * * * php /var/www/dokuwiki/bin/plugin.php aichat embed
```

`embed` only re-reads pages that changed. After big reorganisations, and after changing
`skipRegex` or `matchRegex`, also run `php bin/plugin.php aichat maintenance`.

### 3.5 The chat button

Put this into the wiki's sidebar page (usually `sidebar`):

```
<aichat button float>Hallo! Fragen Sie mich etwas zu diesem Wiki.</aichat>
```

That shows a chat button in the lower right corner of every page. The text is only the greeting.
`<aichat>…</aichat>` without options embeds the chat directly in a page.

### 3.6 Streaming through the web server

The reasoning and the answer only appear while they are written if nothing between PHP and the
browser collects the reply first. The plugin turns off PHP's own buffers and compression and
sends `X-Accel-Buffering: no`, which nginx respects. Check:

```bash
curl -N -X POST "https://wiki.example.org/lib/exe/ajax.php?call=aichat" \
  --data-urlencode "question=a question the wiki answers" \
  --data-urlencode "history=[]" --data-urlencode "stream=1"
```

Lines like `{"type":"thinking","text":"..."}` should scroll by one at a time, ending with one
`{"type":"done",...}`. (With `restrict` set, this anonymous test only gets the "not enabled"
answer; test before setting it, or from a logged-in browser.) If everything arrives at once:

- **Apache with PHP-FPM:** add `flushpackets=on` to the `ProxyPassMatch` / `<Proxy "fcgi://...">`
  that hands requests to PHP-FPM, and exclude the call from compression:
  `SetEnvIf Request_URI "lib/exe/ajax\.php" no-gzip=1`.
- **nginx:** normally nothing to do; otherwise `fastcgi_buffering off;` in a location for
  `/lib/exe/ajax.php`.
- **A proxy or CDN in front of the wiki** may buffer as well; ask whoever runs it.

If streaming cannot be made to work, set `streamThinking` off: the chat then answers as upstream
aichat does (a progress bar, then the whole answer), and the model does not reason.

## Tuning

**`similarityThreshold`** decides which wiki chunks count as sources. Look at the scores:

```bash
sudo -u www-data php bin/plugin.php aichat similar "a typical question"
```

In tests with `bge-m3` the right page scored 0.51-0.73 and unrelated pages at most 0.47, so 50
is a good start. Raise it if answers cite unrelated pages; lower it if the chat often says it
found nothing although the wiki has the answer. Only chunks above the threshold are shown to the
model; a question with none gets "no matching pages" instead of an invented answer.

**Access:** the chat only uses pages the person asking may read (DokuWiki's ACLs). The
`~~similar~~` syntax, which lists similar pages, ignores ACLs. Content between
`<ai-ignore>` and `</ai-ignore>` is left out of the index.

## Speed

`check.sh` writes the same 300 tokens twice, once predictable (counting) and once creative,
and compares the speeds. Multi-token prediction pays off on predictable text, so a ratio of 1.4
or more means it works. Measured on an RTX 5090 (the 5070 Ti has about half its memory
bandwidth, so expect roughly half these speeds):

| Model | Predictable | Creative |
|---|---|---|
| `qwen3.5:9b` | 183 tokens/s | 179 tokens/s |
| `qwen3.5:9b-mtp-q4_K_M` | 289 tokens/s | 192 tokens/s |

Answers to typical questions took 1-3 s without reasoning; with streamed reasoning the first
thoughts appeared after about 0.7 s and the answer after 3-10 s.

To compare on this machine, pull the plain model and benchmark both:

```bash
ollama pull qwen3.5:9b
./check.sh --bench qwen3.5:9b qwen3.5:9b-mtp-q4_K_M
```

If the plain model is not slower, switch with `./install.sh --wiki-server <ip> --chat-model qwen3.5:9b`
and change `chatmodel` and `rephrasemodel` in the wiki. Changing the chat model needs no new index.

## Updates

- **Ubuntu** installs security updates automatically, the NVIDIA driver included.
  - **Why the reboot:** an updated driver only takes effect after a reboot, and until then
    `nvidia-smi` fails. Ollama kept answering in that state on the lab server, but a reboot is
    still due. So the machine reboots at **03:30** when an update asks for one, and the wiki chat
    is unavailable for about a minute. `check.sh` warns while a reboot is pending.
  - **Not holding the driver back:** that would be worse. A new kernel's NVIDIA module needs the
    matching driver libraries, so the machine would boot without a GPU after the next kernel
    update.
  - **Rebooting by hand instead:** `./install.sh --wiki-server <ip> --no-auto-reboot`.
- **Ollama:** `curl -fsSL https://ollama.com/install.sh | sh`, then `sudo systemctl restart ollama`
  and `./check.sh`. The settings drop-in survives updates.
- **Models:** `ollama pull <name>`. A different **embedding** model needs a new index:
  `php bin/plugin.php aichat embed --clear`.
- **The gate:** `git pull` in the checkout, then `./install.sh --update`.
- **The plugin:** see [dokuwiki-plugin/README.md](dokuwiki-plugin/README.md).
- **New token** (e.g. after someone left):
  ```bash
  NEW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sudo sed -i "s/^AICHAT_GATE_TOKEN=.*/AICHAT_GATE_TOKEN=$NEW/" /etc/aichat-gate.env
  sudo systemctl restart aichat-gate && echo "$NEW"
  ```
  and put it into `ollama_apikey` in the wiki.

## Troubleshooting

Logs on the AI machine: `sudo journalctl -u aichat-gate -u ollama --since today`. The gate logs
one line per request (path, model, status, duration), never the questions. On the wiki server,
**Admin → Log Viewer → error** shows the plugin's errors.

| Symptom | Cause and fix |
|---|---|
| Chat says "Sorry, something went wrong" or "API returned no response" | The wiki server does not reach the gate: run the connection test (3.3); `sudo systemctl status aichat-gate`; `sudo ufw status` |
| "missing or wrong token" | `ollama_apikey` does not match `/etc/aichat-gate.env` |
| "... is not available through this gate" | A plugin update calls something new; tell whoever maintains this repository (the gate's `ALLOWED` list) |
| The chat never finds sources | Index empty (`aichat info`) or `similarityThreshold` too high |
| Answers cite unrelated pages | `similarityThreshold` too low |
| Reasoning only appears at the end | The web server buffers (3.6) |
| Answers in the wrong language | Check `customprompt` (3.2) |
| Slow answers | `./check.sh`: a FAIL "layers run on the CPU" means the models do not fit; lower `--context` |
| `nvidia-smi` fails | The NVIDIA driver was updated and the reboot is still pending (03:30, or `--no-auto-reboot`): reboot |
| After installing the driver, `nvidia-smi` still fails after the reboot | Secure Boot: the MOK enrollment screen was skipped. Run `sudo mokutil --import /var/lib/shim-signed/mok/MOK.der`, reboot, choose *Enroll MOK* |
| "Ollama uses N% of a CPU core while idle" (WARN) | An open Ollama issue in recent versions; harmless for answers, but update Ollama when a fix is out |
| Chat shows "not enabled for you" | The `restrict` setting |

## Later: the aiagent plugin

aiagent is aichat's successor (tool use, editing, its own streaming). It is only available
through CosmoCode's paid partner program and has not been tested here. The AI machine can stay
as it is; on the wiki side, per its documentation: PHP 8.2 or newer, install aiagent,
`php bin/plugin.php aiagent_config migrate`, replace `<aichat>` with `<aiagent>` in pages and the
sidebar, and rebuild the index. aichat and aiagent cannot be installed at the same time. The gate
already passes the OpenAI-style routes (`/v1/...`) in case aiagent uses them; check its model
settings for the context size and reasoning, which the gate cannot adjust on those routes.
