import json
import os
import re
import sys
import threading
import time
import tkinter as tk
import uuid
from tkinter import filedialog, font as tkfont
from tkinter import messagebox, ttk

import requests

import meeting
import theme

APP_TITLE = "BrainLabLLM"


def get_base_dir():
    """Directory containing the exe (or this script) - for shipped, admin-editable config."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_user_data_dir():
    """Writable per-user directory for chat history and settings, independent of where
    the app is installed (which may be a read-only location like Program Files)."""
    base = os.environ.get("APPDATA") or get_base_dir()
    path = os.path.join(base, "BrainLabLLM")
    os.makedirs(path, exist_ok=True)
    return path


CONFIG_FILE = os.path.join(get_base_dir(), "config.json")
CHATS_FILE = os.path.join(get_user_data_dir(), "chats.json")
SETTINGS_FILE = os.path.join(get_user_data_dir(), "settings.json")

DEFAULT_CONFIG = {
    "_comment": (
        "Edit these values with Notepad, then restart the app. "
        "ollama_api_url must point at your Ollama server's /api/chat endpoint. "
        "whisper_device can be 'auto', 'cuda' (force GPU), or 'cpu' (force CPU)."
    ),
    "ollama_api_url": "http://10.3.2.112:11434/api/chat",
    "ollama_model": "qwen2.5:32b-coder",
    "whisper_model_size": "medium",
    "whisper_device": "auto",
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            config = dict(DEFAULT_CONFIG)
            config.update(data)
            return config
        except (json.JSONDecodeError, OSError):
            pass
    else:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
    return dict(DEFAULT_CONFIG)


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


CONFIG = load_config()
API_URL = CONFIG["ollama_api_url"]
MODEL = CONFIG["ollama_model"]
WHISPER_MODEL_SIZE = CONFIG["whisper_model_size"]
WHISPER_DEVICE = CONFIG["whisper_device"]

MAX_ATTACHMENT_BYTES = 200_000  # ~200KB per file - generous for code/text, avoids blowing the model's context

CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
INLINE_RE = re.compile(r"`([^`\n]+)`|\*\*([^*]+)\*\*")


def friendly_error_message(exc):
    """Translates common exceptions into plain-language messages for non-technical users."""
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"Can't reach the AI server ({API_URL}). Check that you're connected to the lab network."
    if isinstance(exc, requests.exceptions.Timeout):
        return "The AI server took too long to respond. It may be busy - try again in a moment."
    if isinstance(exc, requests.exceptions.HTTPError):
        return f"The AI server returned an error: {exc}"
    return str(exc)


def query_ollama_stream(messages, should_stop=None):
    payload = {"model": MODEL, "messages": messages, "stream": True}
    with requests.post(API_URL, json=payload, timeout=120, stream=True) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if should_stop and should_stop():
                break
            if not line:
                continue
            chunk = json.loads(line)
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
            if chunk.get("done"):
                break


def chunk_text(text, max_chars=4000):
    """Split text into chunks around max_chars, breaking on sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = []
    current_len = 0
    for sentence in sentences:
        if current_len + len(sentence) > max_chars and current:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(sentence)
        current_len += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def summarize_transcript(transcript, should_stop=None, on_progress=None):
    """Map-reduce summarization over a full meeting transcript.

    Chunks the transcript (so arbitrarily long meetings stay within the
    model's context window), summarizes each chunk independently (map),
    then reduces the chunk summaries into structured notes. For a short
    transcript that's already a single chunk, the map step is skipped and
    the reduce step runs directly on the raw text.
    """
    chunks = chunk_text(transcript)
    on_progress = on_progress or (lambda msg: None)

    if len(chunks) == 1:
        chunk_summaries = [chunks[0]]
    else:
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            on_progress(f"Summarizing part {i + 1}/{len(chunks)}...")
            prompt = [
                {
                    "role": "user",
                    "content": (
                        "Summarize this excerpt from a meeting transcript into a compact list "
                        "of bullet points capturing key statements, decisions, and action items. "
                        "Be concise.\n\n" + chunk
                    ),
                }
            ]
            summary = "".join(query_ollama_stream(prompt, should_stop=should_stop))
            chunk_summaries.append(summary)
            if should_stop and should_stop():
                return ""

    on_progress("Generating final notes...")
    combined = "\n\n".join(chunk_summaries)
    reduce_prompt = [
        {
            "role": "user",
            "content": (
                "Based on these meeting notes, produce a structured summary with three "
                "sections: 'Key Points', 'Decisions', and 'Action Items'. Use markdown bullet "
                "points under each heading. If a section has nothing relevant, write "
                "'None noted.' under it.\n\n" + combined
            ),
        }
    ]
    return "".join(query_ollama_stream(reduce_prompt, should_stop=should_stop))


def new_conversation(title="New chat"):
    return {"id": uuid.uuid4().hex[:8], "title": title, "messages": []}


def _migrate_legacy_chats_file(path):
    """One-time migration: earlier versions stored chats.json next to the
    script/exe. If the new per-user location has nothing yet but an old
    file exists there, copy it over instead of silently losing history."""
    if os.path.exists(path):
        return
    legacy_path = os.path.join(get_base_dir(), "chats.json")
    if os.path.exists(legacy_path):
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
        except OSError:
            pass


def load_conversations(path=CHATS_FILE):
    _migrate_legacy_chats_file(path)
    if not os.path.exists(path):
        return [new_conversation()]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return [new_conversation()]


def save_conversations(conversations, path=CHATS_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conversations, f, indent=2, ensure_ascii=False)


class ChatApp:
    def __init__(self, root):
        self.root = root
        self.conversations = load_conversations()
        self.current = self.conversations[0]
        self.messages = self.current["messages"]
        self.waiting = False
        self.generation_token = 0
        self.pending_start = None

        self.meeting_session = None
        self.meeting_recording = False
        self.meeting_start_time = None
        self._meeting_timer_job = None
        self.meeting_transcript_text = ""
        self.meeting_summary_text = ""
        self.meeting_summary_token = 0
        self.meeting_summarizing = False

        root.title(APP_TITLE)
        if not getattr(sys, "frozen", False):
            # In dev mode, set the icon explicitly; the packaged exe already
            # has it embedded as a PE resource via PyInstaller's --icon flag.
            icon_path = os.path.join(get_base_dir(), "app_icon.ico")
            if os.path.exists(icon_path):
                try:
                    root.iconbitmap(icon_path)
                except tk.TclError:
                    pass
        root.geometry("980x680")
        root.minsize(680, 440)
        root.configure(bg=theme.BG_APP)

        base_font = tkfont.nametofont("TkDefaultFont")
        base_font.configure(family=theme.FONT_FAMILY, size=10)
        self.style = theme.setup_style(root)

        self._build_menu()
        self._build_widgets()
        self._refresh_sidebar()
        self._render_history()
        self._update_action_states()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Control-comma>", lambda e: self.open_settings())

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Settings...", command=self.open_settings)
        menubar.add_cascade(label="File", menu=file_menu)

    def open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.geometry("480x260")
        dialog.resizable(False, False)
        dialog.configure(bg=theme.BG_APP)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="AI Server Settings", style="Heading.TLabel").pack(
            pady=(16, 8), padx=16, anchor=tk.W
        )

        form = ttk.Frame(dialog)
        form.pack(fill=tk.X, padx=16)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Server address:").grid(row=0, column=0, sticky=tk.W, pady=4)
        url_var = tk.StringVar(value=CONFIG.get("ollama_api_url", ""))
        ttk.Entry(form, textvariable=url_var).grid(row=0, column=1, pady=4, padx=(8, 0), sticky=tk.EW)

        ttk.Label(form, text="Model name:").grid(row=1, column=0, sticky=tk.W, pady=4)
        model_var = tk.StringVar(value=CONFIG.get("ollama_model", ""))
        ttk.Entry(form, textvariable=model_var).grid(row=1, column=1, pady=4, padx=(8, 0), sticky=tk.EW)

        status_var = tk.StringVar(value="")
        ttk.Label(dialog, textvariable=status_var, style="Secondary.TLabel").pack(pady=(8, 0))

        def test_connection():
            status_var.set("Testing...")
            url = url_var.get()
            model = model_var.get()

            def run():
                try:
                    resp = requests.post(
                        url,
                        json={"model": model, "messages": [{"role": "user", "content": "hi"}], "stream": False},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    dialog.after(0, lambda: status_var.set("Connected successfully."))
                except Exception as exc:
                    dialog.after(0, lambda: status_var.set(f"Failed: {friendly_error_message(exc)}"))

            threading.Thread(target=run, daemon=True).start()

        def save_and_close():
            CONFIG["ollama_api_url"] = url_var.get()
            CONFIG["ollama_model"] = model_var.get()
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(CONFIG, f, indent=2, ensure_ascii=False)
            except OSError as exc:
                messagebox.showerror("Could not save settings", str(exc))
                return
            messagebox.showinfo("Settings saved", "Restart the app for the new settings to take effect.")
            dialog.destroy()

        button_row = ttk.Frame(dialog)
        button_row.pack(pady=16)
        ttk.Button(button_row, text="Test Connection", command=test_connection).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="Save", style="Accent.TButton", command=save_and_close).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

    def _build_widgets(self):
        root = self.root

        self._build_header(root)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        chat_tab = ttk.Frame(notebook)
        notebook.add(chat_tab, text="Chat")

        meeting_tab = ttk.Frame(notebook)
        notebook.add(meeting_tab, text="Meeting")
        self._build_meeting_tab(meeting_tab)

        paned = ttk.Panedwindow(chat_tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        sidebar = ttk.Frame(paned, width=220, style="Sidebar.TFrame")
        paned.add(sidebar, weight=0)

        main_area = ttk.Frame(paned)
        paned.add(main_area, weight=1)

        ttk.Button(sidebar, text="+  New chat", style="Accent.TButton", command=self.new_chat).pack(
            fill=tk.X, padx=10, pady=(12, 8)
        )

        self.chat_list = tk.Listbox(
            sidebar,
            exportselection=False,
            activestyle="none",
            bg=theme.BG_SIDEBAR,
            fg=theme.TEXT_ON_DARK,
            selectbackground=theme.BG_SIDEBAR_ITEM_SELECTED,
            selectforeground="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            font=(theme.FONT_FAMILY, 10),
            relief=tk.FLAT,
        )
        self.chat_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=3)
        self.chat_list.bind("<<ListboxSelect>>", self._on_select_chat)

        self.delete_button = ttk.Button(
            sidebar, text="🗑  Delete chat", style="Ghost.TButton", command=self.delete_chat
        )
        self.delete_button.pack(fill=tk.X, padx=10, pady=(8, 12))

        self.title_var = tk.StringVar()
        ttk.Label(main_area, textvariable=self.title_var, style="Heading.TLabel").pack(
            fill=tk.X, padx=16, pady=(14, 8)
        )

        # Packed bottom-up (input, then toolbar) BEFORE history_frame, so the
        # input box and toolbar always claim their full required space first
        # and only the scrollable history shrinks when the window gets small
        # - otherwise a tight window can squeeze the input box out of view.
        input_frame = tk.Frame(main_area, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=12)

        self.attachments_row = ttk.Frame(input_frame)
        self.attachments = []

        self.input_row = ttk.Frame(input_frame)
        self.input_row.pack(fill=tk.BOTH, expand=True)
        input_row = self.input_row

        # Fixed-size buttons packed first (from their respective edges) so
        # they always keep their requested space; the expanding Text widget
        # is packed last and only fills whatever remains between them.
        self.attach_button = ttk.Button(input_row, text="📎", width=3, command=self.attach_files)
        self.attach_button.pack(side=tk.LEFT, padx=(6, 0), pady=8)

        self.action_button = ttk.Button(
            input_row, text="Send ➤", style="Accent.TButton", command=self.send_message
        )
        self.action_button.pack(side=tk.RIGHT, padx=8, pady=8)

        self.input = tk.Text(
            input_row,
            height=3,
            wrap=tk.WORD,
            font=(theme.FONT_FAMILY, 10),
            borderwidth=0,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            padx=10,
            pady=8,
            insertbackground=theme.TEXT_PRIMARY,
        )
        self.input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.input.bind("<Return>", self._on_return)
        self.input.focus_set()

        toolbar = ttk.Frame(main_area)
        toolbar.pack(side=tk.BOTTOM, fill=tk.X, padx=16)

        self.regenerate_button = ttk.Button(toolbar, text="↻  Regenerate", command=self.regenerate)
        self.regenerate_button.pack(side=tk.LEFT)

        self.copy_button = ttk.Button(toolbar, text="📋  Copy last reply", command=self.copy_last_reply)
        self.copy_button.pack(side=tk.LEFT, padx=(6, 0))

        self.status_var = tk.StringVar(value="Enter to send, Shift+Enter for a new line")
        ttk.Label(toolbar, textvariable=self.status_var, style="Secondary.TLabel").pack(side=tk.RIGHT)

        history_frame = tk.Frame(main_area, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        history_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        scrollbar = ttk.Scrollbar(history_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history = tk.Text(
            history_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            borderwidth=0,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            padx=16,
            pady=14,
            spacing3=4,
            yscrollcommand=scrollbar.set,
        )
        self.history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.history.yview)
        self._configure_message_tags(self.history)

    def _build_header(self, root):
        header = tk.Frame(root, bg=theme.BG_APP, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        logo = tk.Canvas(header, width=34, height=34, bg=theme.BG_APP, highlightthickness=0)
        logo.pack(side=tk.LEFT, padx=(18, 10), pady=11)
        logo.create_oval(1, 1, 33, 33, fill=theme.ACCENT, outline="")
        logo.create_text(17, 17, text="AI", fill="#FFFFFF", font=(theme.FONT_FAMILY, 11, "bold"))

        title_frame = tk.Frame(header, bg=theme.BG_APP)
        title_frame.pack(side=tk.LEFT, pady=6)
        tk.Label(
            title_frame, text=APP_TITLE, bg=theme.BG_APP, fg=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 13, "bold")
        ).pack(anchor=tk.W)
        tk.Label(
            title_frame,
            text=f"{MODEL}  ·  running on lab hardware",
            bg=theme.BG_APP,
            fg=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 8),
        ).pack(anchor=tk.W)

        ttk.Separator(root, orient=tk.HORIZONTAL).pack(fill=tk.X)

    def _configure_message_tags(self, widget):
        widget.tag_configure(
            "user_label", foreground=theme.ACCENT_TEXT, font=(theme.FONT_FAMILY, 10, "bold"), spacing1=10
        )
        widget.tag_configure(
            "assistant_label", foreground=theme.SUCCESS_TEXT, font=(theme.FONT_FAMILY, 10, "bold"), spacing1=10
        )
        widget.tag_configure(
            "user_bubble",
            background=theme.ACCENT_LIGHT,
            font=(theme.FONT_FAMILY, 10),
            lmargin1=4,
            lmargin2=4,
            rmargin=60,
            spacing3=2,
        )
        widget.tag_configure(
            "assistant_bubble",
            background="#F0F1F6",
            font=(theme.FONT_FAMILY, 10),
            lmargin1=4,
            lmargin2=4,
            rmargin=60,
            spacing3=2,
        )
        widget.tag_configure("body", font=(theme.FONT_FAMILY, 10))
        widget.tag_configure("bold", font=(theme.FONT_FAMILY, 10, "bold"))
        widget.tag_configure(
            "inline_code", font=(theme.FONT_MONO, 10), background=theme.INLINE_CODE_BG, foreground=theme.INLINE_CODE_TEXT
        )
        widget.tag_configure(
            "code_block",
            font=(theme.FONT_MONO, 10),
            background=theme.CODE_BG,
            foreground=theme.CODE_TEXT,
            lmargin1=14,
            lmargin2=14,
            rmargin=40,
            spacing1=6,
            spacing3=6,
        )
        widget.tag_configure("pending", foreground=theme.TEXT_SECONDARY, font=(theme.FONT_FAMILY, 10, "italic"))
        widget.tag_configure("error", foreground=theme.DANGER_TEXT, font=(theme.FONT_FAMILY, 10))
        widget.tag_configure(
            "empty_state", foreground=theme.TEXT_SECONDARY, font=(theme.FONT_FAMILY, 11), justify=tk.CENTER
        )
        # Code/inline-code backgrounds must win over the bubble tint for any
        # overlapping range, since Text tag priority follows configure order.
        widget.tag_raise("inline_code")
        widget.tag_raise("code_block")
        widget.tag_raise("bold")
        widget.tag_raise("error")

    def _on_return(self, event):
        if event.state & 0x1:
            return
        self.send_message()
        return "break"

    def _refresh_sidebar(self):
        self.chat_list.delete(0, tk.END)
        for conv in self.conversations:
            self.chat_list.insert(tk.END, conv["title"])
        index = self.conversations.index(self.current)
        self.chat_list.selection_clear(0, tk.END)
        self.chat_list.selection_set(index)
        self.title_var.set(self.current["title"])

    def _on_select_chat(self, event):
        selection = self.chat_list.curselection()
        if not selection or self.waiting:
            self._refresh_sidebar()
            return
        self.current = self.conversations[selection[0]]
        self.messages = self.current["messages"]
        self.title_var.set(self.current["title"])
        self._render_history()
        self._update_action_states()

    def new_chat(self):
        if self.waiting:
            return
        conv = new_conversation()
        self.conversations.insert(0, conv)
        self.current = conv
        self.messages = conv["messages"]
        self._refresh_sidebar()
        self._render_history()
        self._update_action_states()
        save_conversations(self.conversations)
        self.input.focus_set()

    def delete_chat(self):
        if self.waiting:
            return
        if not messagebox.askyesno("Delete chat", f'Delete "{self.current["title"]}"?'):
            return
        self.conversations.remove(self.current)
        if not self.conversations:
            self.conversations.append(new_conversation())
        self.current = self.conversations[0]
        self.messages = self.current["messages"]
        self._refresh_sidebar()
        self._render_history()
        self._update_action_states()
        save_conversations(self.conversations)

    def attach_files(self):
        paths = filedialog.askopenfilenames(title="Attach files")
        for path in paths:
            self._add_attachment(path)

    def _add_attachment(self, path):
        try:
            with open(path, "rb") as f:
                raw = f.read(MAX_ATTACHMENT_BYTES + 1)
        except OSError as exc:
            messagebox.showerror("Can't attach file", f"Could not read this file:\n\n{exc}")
            return
        truncated = len(raw) > MAX_ATTACHMENT_BYTES
        raw = raw[:MAX_ATTACHMENT_BYTES]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            messagebox.showwarning(
                "Can't attach file",
                f'"{os.path.basename(path)}" doesn\'t look like a text file and can\'t be attached.\n\n'
                "Only text-based files (code, .txt, .md, logs, config files, etc.) are supported.",
            )
            return
        self.attachments.append({"name": os.path.basename(path), "content": text, "truncated": truncated})
        self._refresh_attachments_row()

    def _remove_attachment(self, index):
        del self.attachments[index]
        self._refresh_attachments_row()

    def _refresh_attachments_row(self):
        for widget in self.attachments_row.winfo_children():
            widget.destroy()
        if self.attachments:
            if not self.attachments_row.winfo_ismapped():
                self.attachments_row.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 0), before=self.input_row)
        else:
            self.attachments_row.pack_forget()
            return

        for i, att in enumerate(self.attachments):
            chip = tk.Frame(self.attachments_row, bg=theme.ACCENT_LIGHT)
            chip.pack(side=tk.LEFT, padx=(0, 6), pady=2)
            label_text = f"📄 {att['name']}" + ("  (truncated)" if att["truncated"] else "")
            tk.Label(
                chip,
                text=label_text,
                bg=theme.ACCENT_LIGHT,
                fg=theme.ACCENT_TEXT,
                font=(theme.FONT_FAMILY, 8),
                padx=6,
                pady=3,
            ).pack(side=tk.LEFT)
            remove_btn = tk.Label(
                chip,
                text="✕",
                bg=theme.ACCENT_LIGHT,
                fg=theme.ACCENT_TEXT,
                font=(theme.FONT_FAMILY, 8, "bold"),
                cursor="hand2",
                padx=6,
            )
            remove_btn.pack(side=tk.LEFT)
            remove_btn.bind("<Button-1>", lambda e, idx=i: self._remove_attachment(idx))

    def _build_message_with_attachments(self, text):
        if not self.attachments:
            return text
        parts = []
        for att in self.attachments:
            note = "  (truncated)" if att["truncated"] else ""
            parts.append(f"📄 {att['name']}{note}:\n```\n{att['content']}\n```")
        if text:
            parts.append(text)
        return "\n\n".join(parts)

    def send_message(self):
        if self.waiting:
            return
        text = self.input.get("1.0", tk.END).strip()
        if not text and not self.attachments:
            return
        self.input.delete("1.0", tk.END)
        title_hint = text or self.attachments[0]["name"]
        combined = self._build_message_with_attachments(text)
        self.attachments = []
        self._refresh_attachments_row()
        self._add_user_message(combined, title_hint)
        self._start_generation()

    def _add_user_message(self, text, title_hint=None):
        if self.current["title"] == "New chat":
            hint = title_hint if title_hint is not None else text
            self.current["title"] = hint[:40] + ("…" if len(hint) > 40 else "")
            self._refresh_sidebar()
        self.messages.append({"role": "user", "content": text})
        self._append_turn("You", text, "user_label")
        save_conversations(self.conversations)

    def regenerate(self):
        if self.waiting or not self.messages or self.messages[-1]["role"] != "assistant":
            return
        self.messages.pop()
        self._render_history()
        self._start_generation()

    def _start_generation(self):
        self.generation_token += 1
        token = self.generation_token
        self.stream_buffer = ""
        self._append_pending()
        self._set_waiting(True)
        threading.Thread(target=self._fetch, args=(list(self.messages), token), daemon=True).start()

    def _fetch(self, messages, token):
        try:
            for chunk in query_ollama_stream(messages, should_stop=lambda: token != self.generation_token):
                if token != self.generation_token:
                    return
                self.root.after(0, self._on_chunk, token, chunk)
        except Exception as exc:
            if token == self.generation_token:
                self.root.after(0, self._on_error, token, exc)
            return
        if token == self.generation_token:
            self.root.after(0, self._on_stream_complete, token)

    def _on_chunk(self, token, chunk):
        if token != self.generation_token:
            return
        self.stream_buffer += chunk
        self.history.config(state=tk.NORMAL)
        self.history.insert(tk.END, chunk, ("assistant_bubble", "body"))
        self.history.config(state=tk.DISABLED)
        self.history.see(tk.END)

    def _on_stream_complete(self, token):
        if token != self.generation_token:
            return
        self.messages.append({"role": "assistant", "content": self.stream_buffer})
        self._render_history()
        self._set_waiting(False)
        save_conversations(self.conversations)

    def _on_error(self, token, exc):
        if token != self.generation_token:
            return
        self._render_history()
        self._append_turn("Assistant", f"[{friendly_error_message(exc)}]", "assistant_label", body_tag="error")
        self._set_waiting(False)

    def stop_generation(self):
        if not self.waiting:
            return
        self.generation_token += 1
        if self.stream_buffer:
            self.messages.append({"role": "assistant", "content": self.stream_buffer + " [stopped]"})
        self._render_history()
        self._set_waiting(False)
        save_conversations(self.conversations)

    def copy_last_reply(self):
        for msg in reversed(self.messages):
            if msg["role"] == "assistant":
                self.root.clipboard_clear()
                self.root.clipboard_append(msg["content"])
                return

    def _build_meeting_tab(self, tab):
        device_row = ttk.Frame(tab)
        device_row.pack(fill=tk.X, padx=16, pady=(16, 8))

        ttk.Label(device_row, text="Microphone:", style="SectionTitle.TLabel").pack(side=tk.LEFT)

        self._meeting_devices = []
        self.meeting_device_var = tk.StringVar()
        self.meeting_device_combo = ttk.Combobox(
            device_row, textvariable=self.meeting_device_var, state="readonly", width=42
        )
        self.meeting_device_combo.pack(side=tk.LEFT, padx=(8, 8))
        self.meeting_device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        self.meeting_test_button = ttk.Button(
            device_row, text="Test Microphone", command=self.test_meeting_microphone
        )
        self.meeting_test_button.pack(side=tk.LEFT)

        self._refresh_device_list()

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, padx=16, pady=(0, 12))

        self.meeting_button = ttk.Button(
            toolbar, text="●  Record", style="Accent.TButton", command=self.toggle_meeting_recording
        )
        self.meeting_button.pack(side=tk.LEFT)

        self.meeting_timer_var = tk.StringVar(value="00:00")
        ttk.Label(toolbar, textvariable=self.meeting_timer_var, font=(theme.FONT_FAMILY, 12, "bold")).pack(
            side=tk.LEFT, padx=(14, 0)
        )

        self.meeting_device_used_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.meeting_device_used_var, style="Secondary.TLabel").pack(
            side=tk.LEFT, padx=(14, 0)
        )

        self.meeting_summarize_button = ttk.Button(
            toolbar, text="✨  Summarize", command=self.summarize_meeting, state=tk.DISABLED
        )
        self.meeting_summarize_button.pack(side=tk.LEFT, padx=(16, 0))

        self.meeting_save_button = ttk.Button(
            toolbar, text="💾  Save to chat history", command=self.save_meeting, state=tk.DISABLED
        )
        self.meeting_save_button.pack(side=tk.LEFT, padx=(6, 0))

        self.meeting_export_button = ttk.Button(
            toolbar, text="📤  Export .txt", command=self.export_meeting, state=tk.DISABLED
        )
        self.meeting_export_button.pack(side=tk.LEFT, padx=(6, 0))

        self.meeting_status_var = tk.StringVar(value="Not recording")
        ttk.Label(toolbar, textvariable=self.meeting_status_var, style="Secondary.TLabel").pack(
            side=tk.RIGHT
        )

        paned = ttk.Panedwindow(tab, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        transcript_frame = ttk.Frame(paned)
        paned.add(transcript_frame, weight=3)

        ttk.Label(transcript_frame, text="TRANSCRIPT", style="SectionTitle.TLabel").pack(
            fill=tk.X, pady=(0, 4)
        )
        transcript_body = tk.Frame(
            transcript_frame, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1
        )
        transcript_body.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(transcript_body)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.meeting_transcript = tk.Text(
            transcript_body,
            wrap=tk.WORD,
            state=tk.DISABLED,
            borderwidth=0,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            padx=14,
            pady=12,
            font=(theme.FONT_FAMILY, 10),
            yscrollcommand=scrollbar.set,
        )
        self.meeting_transcript.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.meeting_transcript.yview)
        self.meeting_transcript.tag_configure("placeholder", foreground=theme.TEXT_SECONDARY)
        self.meeting_transcript.config(state=tk.NORMAL)
        self.meeting_transcript.insert(tk.END, "🎙  No recording yet — click Record to start.", "placeholder")
        self.meeting_transcript.config(state=tk.DISABLED)

        summary_frame = ttk.Frame(paned)
        paned.add(summary_frame, weight=2)

        ttk.Label(summary_frame, text="SUMMARY", style="SectionTitle.TLabel").pack(fill=tk.X, pady=(8, 4))
        summary_body = tk.Frame(
            summary_frame, bg=theme.SUCCESS_LIGHT, highlightbackground=theme.BORDER, highlightthickness=1
        )
        summary_body.pack(fill=tk.BOTH, expand=True)

        summary_scrollbar = ttk.Scrollbar(summary_body)
        summary_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.meeting_summary = tk.Text(
            summary_body,
            wrap=tk.WORD,
            state=tk.DISABLED,
            borderwidth=0,
            bg=theme.SUCCESS_LIGHT,
            fg=theme.TEXT_PRIMARY,
            padx=14,
            pady=12,
            font=(theme.FONT_FAMILY, 10),
            yscrollcommand=summary_scrollbar.set,
        )
        self.meeting_summary.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        summary_scrollbar.config(command=self.meeting_summary.yview)
        self.meeting_summary.tag_configure("placeholder", foreground=theme.SUCCESS_TEXT)
        self.meeting_summary.config(state=tk.NORMAL)
        self.meeting_summary.insert(tk.END, "✨  Your summary will appear here after recording.", "placeholder")
        self.meeting_summary.config(state=tk.DISABLED)

    def _refresh_device_list(self):
        devices = meeting.list_input_devices()
        self._meeting_devices = devices
        labels = [name for _, name in devices]
        self.meeting_device_combo["values"] = labels

        settings = load_settings()
        saved_name = settings.get("last_device_name")
        selected_label = saved_name if saved_name in labels else None
        if selected_label is None:
            try:
                default_index = meeting.find_input_device()
                for idx, name in devices:
                    if idx == default_index:
                        selected_label = name
                        break
            except RuntimeError:
                pass
        if selected_label is None and labels:
            selected_label = labels[0]
        if selected_label:
            self.meeting_device_var.set(selected_label)

    def _on_device_selected(self, event=None):
        settings = load_settings()
        settings["last_device_name"] = self.meeting_device_var.get()
        save_settings(settings)

    def _get_selected_device_index(self):
        name = self.meeting_device_var.get()
        for idx, dname in self._meeting_devices:
            if dname == name:
                return idx
        return None

    def test_meeting_microphone(self):
        device = self._get_selected_device_index()
        if device is None:
            messagebox.showwarning("No microphone selected", "Please select a microphone first.")
            return
        self.meeting_test_button.config(state=tk.DISABLED, text="Testing... (speak now)")

        def run():
            try:
                peak, rms = meeting.test_microphone(device, duration=2.5)
            except Exception as exc:
                self.root.after(0, self._on_mic_test_result, None, None, exc)
                return
            self.root.after(0, self._on_mic_test_result, peak, rms, None)

        threading.Thread(target=run, daemon=True).start()

    def _on_mic_test_result(self, peak, rms, exc):
        self.meeting_test_button.config(state=tk.NORMAL, text="Test Microphone")
        if exc is not None:
            messagebox.showerror("Microphone test failed", f"Could not access this microphone:\n\n{exc}")
            return
        if peak < 0.01:
            messagebox.showwarning(
                "No sound detected",
                "The microphone didn't pick up any sound during the test.\n\n"
                "Check that:\n"
                "• The correct microphone is selected above\n"
                "• It isn't muted (check Windows Sound settings → Recording)\n"
                "• You spoke during the 2.5 second test",
            )
        else:
            level_pct = min(100, int(peak * 100))
            messagebox.showinfo(
                "Microphone working", f"Sound detected (peak level: {level_pct}%).\n\nYou're ready to record."
            )

    def toggle_meeting_recording(self):
        if self.meeting_recording:
            self._stop_meeting_recording()
        else:
            self._start_meeting_recording()

    def _start_meeting_recording(self):
        device = self._get_selected_device_index()
        if device is None:
            messagebox.showwarning("No microphone selected", "Please select a microphone before recording.")
            return

        self.meeting_transcript.config(state=tk.NORMAL)
        self.meeting_transcript.delete("1.0", tk.END)
        self.meeting_transcript.config(state=tk.DISABLED)
        self.meeting_summary.config(state=tk.NORMAL)
        self.meeting_summary.delete("1.0", tk.END)
        self.meeting_summary.config(state=tk.DISABLED)
        self.meeting_transcript_text = ""
        self.meeting_summary_text = ""
        self.meeting_summary_token += 1
        self.meeting_summarize_button.config(state=tk.DISABLED)
        self.meeting_save_button.config(state=tk.DISABLED)
        self.meeting_export_button.config(state=tk.DISABLED)
        self.meeting_device_used_var.set("")

        self.meeting_status_var.set("Loading model...")
        self.meeting_button.config(state=tk.DISABLED)
        self.meeting_device_combo.config(state=tk.DISABLED)
        self.meeting_test_button.config(state=tk.DISABLED)

        self.meeting_session = meeting.MeetingSession(
            self.root,
            device=device,
            model_size=WHISPER_MODEL_SIZE,
            device_preference=WHISPER_DEVICE,
            on_transcript=lambda text: self.root.after(0, self._on_meeting_transcript, text),
            on_status=lambda msg: self.root.after(0, self._on_meeting_status, msg),
            on_device_ready=lambda device_used: self.root.after(0, self._on_meeting_device_ready, device_used),
            on_recording_started=lambda: self.root.after(0, self._on_meeting_started),
            on_recording_failed=lambda: self.root.after(0, self._on_meeting_start_failed),
        )
        self.meeting_session.start()

    def _on_meeting_started(self):
        self.meeting_recording = True
        self.meeting_start_time = time.time()
        self.meeting_button.config(text="⏹  Stop", style="Danger.TButton", state=tk.NORMAL)
        self._tick_meeting_timer()

    def _on_meeting_start_failed(self):
        self.meeting_button.config(text="●  Record", style="Accent.TButton", state=tk.NORMAL)
        self.meeting_device_combo.config(state="readonly")
        self.meeting_test_button.config(state=tk.NORMAL)

    def _on_meeting_device_ready(self, device_used):
        label = "GPU" if device_used == "cuda" else "CPU"
        self.meeting_device_used_var.set(f"Whisper: {label}")

    def _stop_meeting_recording(self):
        self.meeting_recording = False
        if self._meeting_timer_job is not None:
            self.root.after_cancel(self._meeting_timer_job)
            self._meeting_timer_job = None
        self.meeting_button.config(text="●  Record", style="Accent.TButton", state=tk.DISABLED)
        self.meeting_status_var.set("Stopping...")
        session = self.meeting_session

        def stop_session():
            if session is not None:
                session.stop()

        threading.Thread(target=stop_session, daemon=True).start()

    def _tick_meeting_timer(self):
        if not self.meeting_recording:
            return
        elapsed = int(time.time() - self.meeting_start_time)
        self.meeting_timer_var.set(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        self._meeting_timer_job = self.root.after(1000, self._tick_meeting_timer)

    def _on_meeting_transcript(self, text):
        self.meeting_transcript_text = text
        self.meeting_transcript.config(state=tk.NORMAL)
        self.meeting_transcript.delete("1.0", tk.END)
        self.meeting_transcript.insert(tk.END, text if text else "(no speech detected)")
        self.meeting_transcript.config(state=tk.DISABLED)
        self.meeting_button.config(state=tk.NORMAL)
        self.meeting_device_combo.config(state="readonly")
        self.meeting_test_button.config(state=tk.NORMAL)
        if text:
            self.meeting_summarize_button.config(state=tk.NORMAL)
            self.meeting_save_button.config(state=tk.NORMAL)
            self.meeting_export_button.config(state=tk.NORMAL)

    def _on_meeting_status(self, msg):
        self.meeting_status_var.set(msg)

    def summarize_meeting(self):
        if self.meeting_summarizing or not self.meeting_transcript_text:
            return
        self.meeting_summary_token += 1
        token = self.meeting_summary_token
        self.meeting_summarizing = True
        self.meeting_summarize_button.config(state=tk.DISABLED)
        self.meeting_summary.config(state=tk.NORMAL)
        self.meeting_summary.delete("1.0", tk.END)
        self.meeting_summary.config(state=tk.DISABLED)

        transcript = self.meeting_transcript_text

        def run():
            try:
                summary = summarize_transcript(
                    transcript,
                    should_stop=lambda: token != self.meeting_summary_token,
                    on_progress=lambda msg: self.root.after(0, self._on_summary_progress, token, msg),
                )
            except Exception as exc:
                self.root.after(0, self._on_summary_error, token, exc)
                return
            self.root.after(0, self._on_summary_complete, token, summary)

        threading.Thread(target=run, daemon=True).start()

    def _on_summary_progress(self, token, msg):
        if token != self.meeting_summary_token:
            return
        self.meeting_status_var.set(msg)

    def _on_summary_complete(self, token, summary):
        if token != self.meeting_summary_token:
            return
        self.meeting_summary_text = summary
        self.meeting_summary.config(state=tk.NORMAL)
        self.meeting_summary.delete("1.0", tk.END)
        self.meeting_summary.insert(tk.END, summary)
        self.meeting_summary.config(state=tk.DISABLED)
        self.meeting_status_var.set("Done")
        self.meeting_summarizing = False
        self.meeting_summarize_button.config(state=tk.NORMAL)

    def _on_summary_error(self, token, exc):
        if token != self.meeting_summary_token:
            return
        self.meeting_status_var.set(f"Summary failed: {friendly_error_message(exc)}")
        self.meeting_summarizing = False
        self.meeting_summarize_button.config(state=tk.NORMAL)

    def save_meeting(self):
        if not self.meeting_transcript_text:
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        conv = new_conversation(title=f"Meeting {timestamp}")
        conv["transcript"] = self.meeting_transcript_text
        content = f"**Transcript**\n\n{self.meeting_transcript_text}"
        if self.meeting_summary_text:
            content += f"\n\n**Summary**\n\n{self.meeting_summary_text}"
        conv["messages"].append({"role": "assistant", "content": content})
        self.conversations.insert(0, conv)
        save_conversations(self.conversations)
        self.meeting_status_var.set(f"Saved to chat history as \"{conv['title']}\"")
        self._refresh_sidebar()

    def export_meeting(self):
        if not self.meeting_transcript_text:
            return
        timestamp = time.strftime("%Y-%m-%d_%H-%M")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"meeting_{timestamp}.txt",
            filetypes=[("Text file", "*.txt")],
            title="Export meeting notes",
        )
        if not path:
            return
        content = f"Transcript\n{'=' * 40}\n\n{self.meeting_transcript_text}\n"
        if self.meeting_summary_text:
            content += f"\nSummary\n{'=' * 40}\n\n{self.meeting_summary_text}\n"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.meeting_status_var.set(f"Exported to {os.path.basename(path)}")
        except OSError as exc:
            messagebox.showerror("Export failed", f"Could not save the file:\n\n{exc}")

    def _on_close(self):
        if self.meeting_recording and self.meeting_session is not None:
            self.meeting_session.stop()
        self.root.destroy()

    def _set_waiting(self, waiting):
        self.waiting = waiting
        if waiting:
            self.action_button.config(text="⏹  Stop", style="Danger.TButton", command=self.stop_generation)
            self.status_var.set("Generating…")
        else:
            self.action_button.config(text="Send ➤", style="Accent.TButton", command=self.send_message)
            self.status_var.set("Enter to send, Shift+Enter for a new line")
        self._update_action_states()

    def _update_action_states(self):
        has_assistant_reply = any(m["role"] == "assistant" for m in self.messages)
        self.regenerate_button.config(
            state=tk.NORMAL if has_assistant_reply and not self.waiting else tk.DISABLED
        )
        self.copy_button.config(state=tk.NORMAL if has_assistant_reply else tk.DISABLED)
        self.delete_button.config(state=tk.DISABLED if self.waiting else tk.NORMAL)

    def _render_history(self):
        self.history.config(state=tk.NORMAL)
        self.history.delete("1.0", tk.END)
        if not self.messages:
            self.history.insert(
                tk.END,
                "💬  Start a conversation\n\nType a message below and press Enter.",
                "empty_state",
            )
        self.history.config(state=tk.DISABLED)
        for msg in self.messages:
            if msg["role"] == "user":
                self._append_turn("You", msg["content"], "user_label")
            else:
                self._append_turn("Assistant", msg["content"], "assistant_label")
        self._update_action_states()

    def _append_turn(self, label, text, label_tag, body_tag=None):
        bubble_tag = "user_bubble" if label_tag == "user_label" else "assistant_bubble"
        self.history.config(state=tk.NORMAL)
        self.history.insert(tk.END, f"{label}\n", label_tag)
        if body_tag:
            self.history.insert(tk.END, f"{text}\n\n", (bubble_tag, body_tag))
        else:
            self._insert_formatted(text, bubble_tag)
            self.history.insert(tk.END, "\n\n")
        self.history.config(state=tk.DISABLED)
        self.history.see(tk.END)

    def _append_pending(self):
        self.history.config(state=tk.NORMAL)
        self.history.insert(tk.END, "Assistant\n", "assistant_label")
        self.history.config(state=tk.DISABLED)
        self.history.see(tk.END)

    def _insert_formatted(self, text, bubble_tag):
        pos = 0
        for m in CODE_BLOCK_RE.finditer(text):
            if m.start() > pos:
                self._insert_inline(text[pos:m.start()], bubble_tag)
            code = m.group(1).rstrip("\n")
            self.history.insert(tk.END, code + "\n", "code_block")
            pos = m.end()
        if pos < len(text):
            self._insert_inline(text[pos:], bubble_tag)

    def _insert_inline(self, segment, bubble_tag):
        pos = 0
        for m in INLINE_RE.finditer(segment):
            if m.start() > pos:
                self.history.insert(tk.END, segment[pos:m.start()], (bubble_tag, "body"))
            if m.group(1) is not None:
                self.history.insert(tk.END, m.group(1), "inline_code")
            else:
                self.history.insert(tk.END, m.group(2), (bubble_tag, "bold"))
            pos = m.end()
        if pos < len(segment):
            self.history.insert(tk.END, segment[pos:], (bubble_tag, "body"))


def main():
    root = tk.Tk()
    ChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
