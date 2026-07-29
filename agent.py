import difflib
import json
import ntpath
import os
import re
import subprocess
import threading

import requests

MAX_TOOL_READ_BYTES = 200_000  # same cap/precedent as main.MAX_ATTACHMENT_BYTES
MAX_LIST_ENTRIES = 500
MAX_SEARCH_RESULTS = 200
MAX_SEARCH_CONTEXT_CHARS = 200
SHELL_TIMEOUT_SECONDS = 60
MAX_DIFF_LINES = 300
MAX_ITERATIONS = 20

IGNORED_DIR_NAMES = {".git", "__pycache__", ".venv", "node_modules", "dist", "build", "site"}


class PathEscapeError(Exception):
    """Raised when a tool-provided path would resolve outside the project root."""

    def __init__(self, user_path):
        self.user_path = user_path
        super().__init__(f"Path escapes the project folder: {user_path!r}")


def resolve_scoped_path(project_root, user_path):
    """Resolve user_path relative to project_root, guaranteeing the result stays
    inside project_root. Raises PathEscapeError on any attempt to leave it.

    Absolute paths are rejected outright (even ones that happen to resolve inside
    root) - the model never legitimately needs to know the real absolute location
    of the project on disk, and this is simpler to reason about than "reject only
    if outside root". Symlinks are resolved (os.path.realpath), so an in-project
    symlink pointing outside root is also blocked - this is a hard security
    boundary, not just a UI nicety.
    """
    if not isinstance(user_path, str) or user_path == "":
        user_path = "."

    if os.path.isabs(user_path) or ntpath.isabs(user_path):
        raise PathEscapeError(user_path)

    # Windows drive-relative form, e.g. "C:foo" - isabs() treats this as relative,
    # but it resolves against a per-drive working directory, not project_root.
    drive, _ = ntpath.splitdrive(user_path)
    if drive:
        raise PathEscapeError(user_path)

    # UNC paths, e.g. "\\\\server\\share\\x" - splitdrive catches "\\\\server\\share"
    # as the drive on some inputs, but guard explicitly in case of odd normalization.
    if user_path.replace("/", "\\").startswith("\\\\"):
        raise PathEscapeError(user_path)

    root_real = os.path.realpath(project_root)
    candidate = os.path.normpath(os.path.join(root_real, user_path))
    candidate_real = os.path.realpath(candidate)

    try:
        common = os.path.commonpath([root_real, candidate_real])
    except ValueError:
        # commonpath raises if the paths are on different drives on Windows -
        # different drive unambiguously means "escaped".
        raise PathEscapeError(user_path)

    if common != root_real:
        raise PathEscapeError(user_path)

    return candidate_real


class ToolError(Exception):
    """A user-facing tool failure that should be reported back to the model as a
    tool result, not raised as an unhandled exception in the agent loop thread."""


def _friendly_tool_error(exc):
    if isinstance(exc, PathEscapeError):
        return f"Error: that path is outside the project folder and cannot be accessed ({exc.user_path!r})."
    if isinstance(exc, ToolError):
        return f"Error: {exc}"
    if isinstance(exc, FileNotFoundError):
        return "Error: file or directory not found."
    if isinstance(exc, IsADirectoryError):
        return "Error: that path is a directory, not a file."
    if isinstance(exc, PermissionError):
        return "Error: permission denied."
    if isinstance(exc, UnicodeDecodeError):
        return "Error: file is not readable as UTF-8 text (likely a binary file)."
    return f"Error: {exc}"


def _should_skip_dir(name):
    return name in IGNORED_DIR_NAMES


def _looks_binary(sample_bytes):
    return b"\x00" in sample_bytes


# --- read-only tools: no approval gate needed in either mode ---

def tool_read_file(project_root, arguments):
    path = arguments.get("path", "")
    start_line = arguments.get("start_line")
    end_line = arguments.get("end_line")

    resolved = resolve_scoped_path(project_root, path)
    if os.path.isdir(resolved):
        raise IsADirectoryError()

    with open(resolved, "rb") as f:
        raw = f.read(MAX_TOOL_READ_BYTES + 1)
    truncated = len(raw) > MAX_TOOL_READ_BYTES
    raw = raw[:MAX_TOOL_READ_BYTES]
    # Universal-newline normalization, to match the text-mode open() used by
    # prepare_write_file/prepare_edit_file - otherwise a file with CRLF line
    # endings (the Windows default) would make edit_file's exact-text matching
    # fail against old_text the model composed from what read_file showed it.
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")

    if start_line is not None or end_line is not None:
        lines = text.splitlines(keepends=True)
        start_idx = max((start_line or 1) - 1, 0)
        end_idx = end_line if end_line is not None else len(lines)
        text = "".join(lines[start_idx:end_idx])

    return {"path": path, "content": text, "truncated": truncated}


def tool_list_directory(project_root, arguments):
    path = arguments.get("path", ".")
    recursive = bool(arguments.get("recursive", False))

    resolved = resolve_scoped_path(project_root, path)
    if not os.path.isdir(resolved):
        raise ToolError("not a directory")

    entries = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(resolved):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            rel_dir = os.path.relpath(dirpath, resolved)
            for name in sorted(dirnames):
                rel = name if rel_dir == "." else os.path.join(rel_dir, name)
                entries.append(rel.replace(os.sep, "/") + "/")
            for name in sorted(filenames):
                rel = name if rel_dir == "." else os.path.join(rel_dir, name)
                entries.append(rel.replace(os.sep, "/"))
            if len(entries) >= MAX_LIST_ENTRIES:
                break
    else:
        with os.scandir(resolved) as it:
            for e in sorted(it, key=lambda x: x.name):
                if e.is_dir() and _should_skip_dir(e.name):
                    continue
                entries.append(e.name + "/" if e.is_dir() else e.name)

    truncated = len(entries) > MAX_LIST_ENTRIES
    entries = entries[:MAX_LIST_ENTRIES]
    return {"path": path, "entries": entries, "truncated": truncated}


def tool_search_code(project_root, arguments):
    pattern = arguments.get("pattern", "")
    path = arguments.get("path", ".")
    case_sensitive = bool(arguments.get("case_sensitive", False))
    max_results = min(int(arguments.get("max_results") or MAX_SEARCH_RESULTS), MAX_SEARCH_RESULTS)

    resolved = resolve_scoped_path(project_root, path)

    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
    except re.error as exc:
        raise ToolError(f"invalid regex pattern: {exc}")

    results = []
    search_root = resolved if os.path.isdir(resolved) else os.path.dirname(resolved)
    files_to_search = []
    if os.path.isfile(resolved):
        files_to_search = [resolved]
    else:
        for dirpath, dirnames, filenames in os.walk(resolved):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            for name in filenames:
                files_to_search.append(os.path.join(dirpath, name))

    for filepath in files_to_search:
        if len(results) >= max_results:
            break
        try:
            with open(filepath, "rb") as f:
                sample = f.read(4096)
                if _looks_binary(sample):
                    continue
                f.seek(0)
                content = (sample + f.read()).decode("utf-8", errors="ignore")
        except OSError:
            continue

        rel_path = os.path.relpath(filepath, project_root).replace(os.sep, "/")
        for lineno, line in enumerate(content.splitlines(), start=1):
            if len(results) >= max_results:
                break
            if regex.search(line):
                snippet = line.strip()[:MAX_SEARCH_CONTEXT_CHARS]
                results.append({"path": rel_path, "line": lineno, "text": snippet})

    return {"pattern": pattern, "matches": results, "truncated": len(results) >= max_results}


# --- write proposal preparation: pure, never touches disk ---

class WriteProposal:
    def __init__(self, rel_path, resolved_path, old_content, new_content):
        self.rel_path = rel_path
        self.resolved_path = resolved_path
        self.old_content = old_content
        self.new_content = new_content


def prepare_write_file(project_root, arguments):
    path = arguments.get("path", "")
    content = arguments.get("content", "")
    if len(content.encode("utf-8")) > MAX_TOOL_READ_BYTES:
        raise ToolError(f"content exceeds the {MAX_TOOL_READ_BYTES}-byte limit for a single write")

    resolved = resolve_scoped_path(project_root, path)
    old_content = None
    if os.path.exists(resolved):
        if os.path.isdir(resolved):
            raise IsADirectoryError()
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            old_content = f.read()

    return WriteProposal(path, resolved, old_content or "", content)


def prepare_edit_file(project_root, arguments):
    path = arguments.get("path", "")
    old_text = arguments.get("old_text", "")
    new_text = arguments.get("new_text", "")

    resolved = resolve_scoped_path(project_root, path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError()

    with open(resolved, "r", encoding="utf-8") as f:
        current = f.read()

    count = current.count(old_text)
    if count == 0:
        raise ToolError("old_text was not found in the file - be exact, or use write_file to replace the whole file")
    if count > 1:
        raise ToolError(
            f"old_text appears {count} times in the file - it must be unique; include more surrounding context"
        )

    new_content = current.replace(old_text, new_text, 1)
    return WriteProposal(path, resolved, current, new_content)


def apply_write(proposal):
    """Actually writes proposal.new_content to disk. Only ever called after
    approval in Auto mode - never called from Planning mode."""
    os.makedirs(os.path.dirname(proposal.resolved_path), exist_ok=True)
    with open(proposal.resolved_path, "w", encoding="utf-8", newline="") as f:
        f.write(proposal.new_content)


def compute_diff(old_text, new_text, path):
    """Returns a list of (tag, line) tuples, tag in {"header","add","remove","context"},
    for rendering a unified diff with colored line tags in a Tk Text widget."""
    lines = list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
            lineterm="",
        )
    )

    truncated = len(lines) > MAX_DIFF_LINES
    lines = lines[:MAX_DIFF_LINES]

    result = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("@@"):
            tag = "header"
        elif stripped.startswith("+++") or stripped.startswith("---"):
            tag = "header"
        elif stripped.startswith("+"):
            tag = "add"
        elif stripped.startswith("-"):
            tag = "remove"
        else:
            tag = "context"
        result.append((tag, stripped))

    if truncated:
        result.append(("header", f"... diff truncated after {MAX_DIFF_LINES} lines ..."))

    return result


# --- shell command: mutating, Auto-mode only, executed directly by the caller
# after approval (there is no "propose without executing" concept for a shell
# command the way there is for a file write) ---

def tool_run_shell_command(project_root, arguments):
    command = arguments.get("command", "")
    cwd_arg = arguments.get("cwd", ".")
    if not command:
        raise ToolError("command is required")

    resolved_cwd = resolve_scoped_path(project_root, cwd_arg)
    if not os.path.isdir(resolved_cwd):
        raise ToolError("cwd is not a directory")

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=resolved_cwd,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"command timed out after {SHELL_TIMEOUT_SECONDS}s")

    stdout = proc.stdout[:20_000]
    stderr = proc.stderr[:20_000]
    return {"command": command, "exit_code": proc.returncode, "stdout": stdout, "stderr": stderr}


READ_ONLY_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a text file within the project folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the project root."},
                    "start_line": {"type": "integer", "description": "Optional 1-based first line to read."},
                    "end_line": {"type": "integer", "description": "Optional 1-based last line to read (inclusive)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories at a path within the project folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the project root. Defaults to '.'."},
                    "recursive": {"type": "boolean", "description": "List all nested files/folders. Defaults to false."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a regex pattern across text files within the project folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression to search for."},
                    "path": {"type": "string", "description": "Path to search within. Defaults to '.'."},
                    "case_sensitive": {"type": "boolean", "description": "Defaults to false."},
                },
                "required": ["pattern"],
            },
        },
    },
]

WRITE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing file's entire contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the project root."},
                    "content": {"type": "string", "description": "The full new contents of the file."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Make a targeted change to an existing file by replacing an exact, unique snippet of its "
                "current content with new content. old_text must match exactly once in the file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the project root."},
                    "old_text": {"type": "string", "description": "Exact existing text to replace (must be unique in the file)."},
                    "new_text": {"type": "string", "description": "Text to replace it with."},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
]

SHELL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_shell_command",
        "description": "Run a shell command within the project folder. Requires user approval before it executes.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The literal shell command to run."},
                "cwd": {"type": "string", "description": "Working directory relative to the project root. Defaults to '.'."},
            },
            "required": ["command"],
        },
    },
}

READ_ONLY_EXECUTORS = {
    "read_file": tool_read_file,
    "list_directory": tool_list_directory,
    "search_code": tool_search_code,
}


def friendly_agent_error(exc):
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Can't reach the AI server. Check that you're connected to the lab network."
    if isinstance(exc, requests.exceptions.Timeout):
        return "The AI server took too long to respond. It may be busy - try again in a moment."
    if isinstance(exc, requests.exceptions.HTTPError):
        return f"The AI server returned an error: {exc}"
    return str(exc)


def query_ollama_chat(api_url, model, messages, tools=None, should_stop=None, timeout=180):
    """Tool-calling-capable sibling of main.query_ollama_stream. Non-streaming,
    since that's the exact request shape confirmed to return structured
    tool_calls for this model - streaming tool-calls' chunk-accumulation
    behavior is unverified and not worth guessing at for v1.

    Returns the response's message dict (role/content/tool_calls), or None if
    should_stop() was already true before the request was sent.
    """
    if should_stop and should_stop():
        return None

    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools

    response = requests.post(api_url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data.get("message", {})


def _summarize_read_result(name, result):
    if name == "read_file":
        n = len(result["content"].splitlines())
        note = " (truncated)" if result.get("truncated") else ""
        return f"Read {result['path']} - {n} line(s){note}"
    if name == "list_directory":
        n = len(result["entries"])
        note = " (truncated)" if result.get("truncated") else ""
        return f"Listed {result['path']} - {n} entrie(s){note}"
    if name == "search_code":
        n = len(result["matches"])
        return f"Searched for {result['pattern']!r} - {n} match(es)"
    return "Done."


class AgentSession:
    """The agentic tool-calling loop, shaped like meeting.MeetingSession:
    constructor takes `root` (anything with .after(delay, func, *args)) plus
    on_xxx callbacks, exposes .start()/.cancel(), owns its own run_token
    (independent of ChatApp.generation_token / MeetingSession.recording_token -
    one counter per independent operation, per the existing codebase idiom).

    Planning mode and Auto mode share this one loop implementation; only
    _handle_write_tool/_handle_shell_tool branch on self.mode.
    """

    def __init__(
        self,
        root,
        project_root,
        api_url,
        model,
        mode="planning",
        on_assistant_text=None,
        on_tool_call_start=None,
        on_tool_call_result=None,
        on_approval_needed=None,
        on_done=None,
        on_error=None,
        on_status=None,
    ):
        self.root = root
        self.project_root = project_root
        self.api_url = api_url
        self.model = model
        self.mode = mode

        self.on_assistant_text = on_assistant_text or (lambda token, text: None)
        self.on_tool_call_start = on_tool_call_start or (lambda token, name, arguments: None)
        self.on_tool_call_result = on_tool_call_result or (lambda token, name, payload: None)
        self.on_approval_needed = on_approval_needed or (lambda token, info: None)
        self.on_done = on_done or (lambda token, content, pending_plan_edits: None)
        self.on_error = on_error or (lambda token, message: None)
        self.on_status = on_status or (lambda token, message: None)

        self.run_token = 0
        self.messages = []
        self.pending_plan_edits = {}  # rel_path -> WriteProposal (most recent for that path)

        self._approval_event = threading.Event()
        self._approval_decision = None

    def _tools_for_mode(self):
        tools = list(READ_ONLY_TOOL_SCHEMAS) + list(WRITE_TOOL_SCHEMAS)
        if self.mode == "auto":
            tools = tools + [SHELL_TOOL_SCHEMA]
        return tools

    def _should_stop(self, token):
        return token != self.run_token

    def start(self, user_instruction):
        self.run_token += 1
        token = self.run_token
        self.messages.append({"role": "user", "content": user_instruction})
        thread = threading.Thread(target=self._run_loop, args=(token,), daemon=True)
        thread.start()
        return token

    def cancel(self):
        self.run_token += 1
        # Unblock a background thread parked in an approval wait, if any -
        # otherwise it would sit blocked pointlessly for the rest of the run
        # (harmless since it's a daemon thread, but pointless).
        self._approval_decision = "cancelled"
        self._approval_event.set()

    def submit_approval(self, approved):
        self._approval_decision = "approved" if approved else "rejected"
        self._approval_event.set()

    def _run_loop(self, token):
        try:
            for _ in range(MAX_ITERATIONS):
                if self._should_stop(token):
                    return

                try:
                    message = query_ollama_chat(
                        self.api_url,
                        self.model,
                        self.messages,
                        tools=self._tools_for_mode(),
                        should_stop=lambda: self._should_stop(token),
                    )
                except Exception as exc:
                    self.root.after(0, self.on_error, token, friendly_agent_error(exc))
                    return

                if message is None or self._should_stop(token):
                    return

                self.messages.append(message)

                content = message.get("content") or ""
                if content:
                    self.root.after(0, self.on_assistant_text, token, content)

                tool_calls = message.get("tool_calls") or []
                if not tool_calls:
                    self.root.after(0, self.on_done, token, content, dict(self.pending_plan_edits))
                    return

                for i, call in enumerate(tool_calls):
                    call_id = call.get("id", "")
                    if self._should_stop(token):
                        # Fill stubs for this and every remaining call in the batch so
                        # self.messages stays well-formed (every tool_call in the last
                        # assistant message has a matching tool response), in case this
                        # session's message history is reused by a later run.
                        for rc in tool_calls[i:]:
                            self.messages.append(
                                {"role": "tool", "tool_call_id": rc.get("id", ""), "content": "Cancelled."}
                            )
                        return

                    fn = call.get("function", {})
                    name = fn.get("name", "")
                    arguments = fn.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                    self.root.after(0, self.on_tool_call_start, token, name, arguments)
                    display_payload, model_content = self._dispatch_tool(token, name, arguments)
                    self.root.after(0, self.on_tool_call_result, token, name, display_payload)
                    self.messages.append({"role": "tool", "tool_call_id": call_id, "content": model_content})

                    if self._should_stop(token):
                        for rc in tool_calls[i + 1 :]:
                            self.messages.append(
                                {"role": "tool", "tool_call_id": rc.get("id", ""), "content": "Cancelled."}
                            )
                        return

            self.root.after(
                0, self.on_status, token, f"Stopped after {MAX_ITERATIONS} steps - send another message to continue."
            )
        except Exception as exc:
            self.root.after(0, self.on_error, token, friendly_agent_error(exc))

    def _dispatch_tool(self, token, name, arguments):
        """Returns (display_payload, model_content) - display_payload is what the
        UI renders (a dict with a "kind" key), model_content is the plain string
        that goes back to the model as the tool result."""
        try:
            if name in READ_ONLY_EXECUTORS:
                result = READ_ONLY_EXECUTORS[name](self.project_root, arguments)
                summary = _summarize_read_result(name, result)
                return {"kind": "text", "summary": summary}, json.dumps(result)

            if name in ("write_file", "edit_file"):
                return self._handle_write_tool(token, name, arguments)

            if name == "run_shell_command":
                return self._handle_shell_tool(token, arguments)

            return {"kind": "text", "summary": f"Unknown tool {name!r}"}, f"Error: unknown tool {name!r}"
        except Exception as exc:
            error_text = _friendly_tool_error(exc)
            return {"kind": "text", "summary": error_text}, error_text

    def _handle_write_tool(self, token, name, arguments):
        try:
            if name == "write_file":
                proposal = prepare_write_file(self.project_root, arguments)
            else:
                proposal = prepare_edit_file(self.project_root, arguments)
        except Exception as exc:
            error_text = _friendly_tool_error(exc)
            return {"kind": "text", "summary": error_text}, error_text

        # Diff against the previously-proposed content for this path if any, not
        # stale on-disk content, so a second edit to the same file in one run
        # composes correctly instead of "undoing" the first proposed edit.
        prior = self.pending_plan_edits.get(proposal.rel_path)
        base_old_content = prior.new_content if prior is not None else proposal.old_content
        diff = compute_diff(base_old_content, proposal.new_content, proposal.rel_path)
        display_payload = {"kind": "diff", "path": proposal.rel_path, "diff": diff}

        if self.mode == "planning":
            self.pending_plan_edits[proposal.rel_path] = proposal
            return display_payload, "Edit captured in the plan (not written to disk). Continue."

        # Auto mode: block this background thread on an approval Event - the Tk
        # main loop is untouched while waiting, so this fits the existing
        # root.after(0, ...) idiom rather than fighting it.
        self._approval_event.clear()
        self._approval_decision = None
        self.root.after(0, self.on_approval_needed, token, {"kind": "file_edit", "path": proposal.rel_path, "diff": diff})
        self._approval_event.wait()

        if self._should_stop(token) or self._approval_decision in ("cancelled", None):
            return display_payload, "Cancelled."
        if self._approval_decision == "rejected":
            declined = "User declined this edit. Do not repeat it unchanged - consider a different approach or ask what to do instead."
            return display_payload, declined

        apply_write(proposal)
        self.pending_plan_edits.pop(proposal.rel_path, None)
        return display_payload, f"Wrote {proposal.rel_path} successfully."

    def _handle_shell_tool(self, token, arguments):
        command = arguments.get("command", "")
        cwd = arguments.get("cwd", ".")
        display_payload = {"kind": "shell_command", "command": command, "cwd": cwd}

        self._approval_event.clear()
        self._approval_decision = None
        self.root.after(0, self.on_approval_needed, token, {"kind": "shell_command", "command": command, "cwd": cwd})
        self._approval_event.wait()

        if self._should_stop(token) or self._approval_decision in ("cancelled", None):
            return display_payload, "Cancelled."
        if self._approval_decision == "rejected":
            declined = "User declined to run this command. Consider a different approach or ask what to do instead."
            return display_payload, declined

        try:
            result = tool_run_shell_command(self.project_root, arguments)
        except Exception as exc:
            error_text = _friendly_tool_error(exc)
            return {"kind": "text", "summary": error_text}, error_text

        result_payload = {"kind": "text", "summary": f"Ran: {command} (exit {result['exit_code']})"}
        return result_payload, json.dumps(result)
