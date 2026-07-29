"""Tests that exercise agent.py against the real lab Ollama server, plus a few
AgentSession tests that mock the model response to check loop control-flow
(iteration cap, path-escape handling) without needing the network."""

import os
import threading
import time
from unittest import mock

import pytest

import agent
from conftest import API_URL, MODEL, requires_lab_server


class SyncRoot:
    """root.after(delay, func, *args) calls func immediately - matches
    MeetingSession/AgentSession's duck-typed root contract, no real Tk needed."""

    def after(self, delay, func, *args):
        func(*args)


def _wait_for(done_holder, timeout=60):
    deadline = time.time() + timeout
    while "done" not in done_holder and time.time() < deadline:
        time.sleep(0.2)
    return "done" in done_holder


@pytest.fixture
def project(tmp_path):
    (tmp_path / "readme.txt").write_text("hello project\n", encoding="utf-8")
    return str(tmp_path)


@requires_lab_server
class TestQueryOllamaChat:
    def test_no_tools_needed_returns_plain_content(self):
        msg = agent.query_ollama_chat(API_URL, MODEL, [{"role": "user", "content": "Reply with exactly: PONG"}])
        assert "PONG" in msg.get("content", "")
        assert not msg.get("tool_calls")

    def test_tool_call_has_expected_shape(self):
        messages = [{"role": "user", "content": "List the files in the current directory using the list_directory tool."}]
        msg = agent.query_ollama_chat(API_URL, MODEL, messages, tools=agent.READ_ONLY_TOOL_SCHEMAS)
        assert msg.get("tool_calls")
        call = msg["tool_calls"][0]
        assert call["function"]["name"] == "list_directory"
        assert isinstance(call["function"]["arguments"], dict)
        assert "id" in call

    def test_should_stop_short_circuits_before_sending(self):
        msg = agent.query_ollama_chat(API_URL, MODEL, [{"role": "user", "content": "hi"}], should_stop=lambda: True)
        assert msg is None


@requires_lab_server
class TestAgentSessionLive:
    def test_multistep_run_lists_and_reads(self, project):
        os.makedirs(os.path.join(project, "sub"), exist_ok=True)
        events = []
        done = {}
        session = agent.AgentSession(
            SyncRoot(),
            project,
            API_URL,
            MODEL,
            mode="planning",
            on_tool_call_start=lambda token, name, args: events.append(name),
            on_done=lambda token, content, pending: done.update(done=True, content=content),
            on_error=lambda token, msg: done.update(done=True, error=msg),
        )
        session.start("List the files in this project, then read readme.txt and report its contents.")
        assert _wait_for(done, timeout=90)
        assert "error" not in done
        assert "list_directory" in events
        assert "read_file" in events

    def test_planning_mode_never_writes_to_disk(self, project):
        done = {}
        session = agent.AgentSession(
            SyncRoot(),
            project,
            API_URL,
            MODEL,
            mode="planning",
            on_done=lambda token, content, pending: done.update(done=True, pending=pending),
            on_error=lambda token, msg: done.update(done=True, error=msg),
        )
        session.start("Edit readme.txt to replace 'hello project' with 'hi project' using the edit_file tool.")
        assert _wait_for(done, timeout=90)
        assert "error" not in done
        assert open(os.path.join(project, "readme.txt")).read() == "hello project\n"
        assert done.get("pending")

    def test_auto_mode_approve_writes_to_disk(self, project):
        done = {}

        def approve(token, info):
            session.submit_approval(True)

        session = agent.AgentSession(
            SyncRoot(),
            project,
            API_URL,
            MODEL,
            mode="auto",
            on_approval_needed=approve,
            on_done=lambda token, content, pending: done.update(done=True),
            on_error=lambda token, msg: done.update(done=True, error=msg),
        )
        session.start("Edit readme.txt to replace 'hello project' with 'hi project' using the edit_file tool.")
        assert _wait_for(done, timeout=90)
        assert "error" not in done
        assert "hi project" in open(os.path.join(project, "readme.txt")).read()

    def test_auto_mode_reject_does_not_write_and_model_adapts(self, project):
        done = {}
        approval_seen = []

        def reject(token, info):
            approval_seen.append(info)
            session.submit_approval(False)

        session = agent.AgentSession(
            SyncRoot(),
            project,
            API_URL,
            MODEL,
            mode="auto",
            on_approval_needed=reject,
            on_done=lambda token, content, pending: done.update(done=True),
            on_error=lambda token, msg: done.update(done=True, error=msg),
        )
        session.start("Edit readme.txt to replace 'hello project' with 'hi project' using the edit_file tool.")
        assert _wait_for(done, timeout=90)
        assert "error" not in done
        assert open(os.path.join(project, "readme.txt")).read() == "hello project\n"
        assert len(approval_seen) >= 1

    def test_cancel_unblocks_pending_approval_wait(self, project):
        approval_seen = threading.Event()

        def slow_approval(token, info):
            approval_seen.set()
            # Deliberately never calls submit_approval - cancel() must unblock it.

        session = agent.AgentSession(
            SyncRoot(), project, API_URL, MODEL, mode="auto", on_approval_needed=slow_approval
        )
        session.start("Edit readme.txt to replace 'hello project' with 'hi project' using the edit_file tool.")
        assert approval_seen.wait(timeout=30)
        session.cancel()
        time.sleep(2)  # give the unblocked thread a moment to actually return - no hang expected


class TestAgentSessionMocked:
    """Control-flow tests that don't need the real server."""

    def test_iteration_cap_stops_cleanly(self, project):
        done = {}
        call_count = {"n": 0}

        def fake_infinite_tool_caller(api_url, model, messages, tools=None, should_stop=None):
            call_count["n"] += 1
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": f"call_{call_count['n']}", "function": {"name": "list_directory", "arguments": {"path": "."}}}
                ],
            }

        with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_infinite_tool_caller):
            session = agent.AgentSession(
                SyncRoot(),
                project,
                "http://fake",
                "fake-model",
                mode="planning",
                on_status=lambda token, msg: done.update(done=True, status=msg),
                on_done=lambda token, content, pending: done.update(done=True, content=content),
                on_error=lambda token, msg: done.update(done=True, error=msg),
            )
            session.start("do something")
            assert _wait_for(done, timeout=30)

        assert "status" in done
        assert call_count["n"] <= agent.MAX_ITERATIONS

    def test_path_escape_is_blocked_and_no_secret_leaks(self, project, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside_secret")
        (outside / "secret.txt").write_text("TOP SECRET", encoding="utf-8")

        responses = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "read_file", "arguments": {"path": "../" + os.path.basename(str(outside)) + "/secret.txt"}}}
                ],
            },
            {"role": "assistant", "content": "Blocked. Stopping."},
        ]
        call_log = []

        def fake_query(api_url, model, messages, tools=None, should_stop=None):
            call_log.append(messages[-1])
            return responses[len(call_log) - 1]

        done = {}
        with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query):
            session = agent.AgentSession(
                SyncRoot(),
                project,
                "http://fake",
                "fake-model",
                mode="auto",
                on_done=lambda token, content, pending: done.update(done=True),
                on_error=lambda token, msg: done.update(done=True, error=msg),
                on_approval_needed=lambda token, info: pytest.fail("path escape should never reach approval"),
            )
            session.start("try to read outside the project")
            assert _wait_for(done, timeout=10)

        assert "error" not in done
        tool_messages = [m for m in session.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "outside the project folder" in tool_messages[0]["content"]
        assert "TOP SECRET" not in tool_messages[0]["content"]
