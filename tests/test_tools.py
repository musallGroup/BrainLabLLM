import os

import pytest

import agent


@pytest.fixture
def project(tmp_path):
    root = tmp_path
    (root / "sub").mkdir()
    (root / "__pycache__").mkdir()
    (root / "sub" / "file.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    (root / "hello.py").write_text("def hello():\n    print('hello world')\n", encoding="utf-8")
    return str(root)


def test_read_file_basic(project):
    result = agent.tool_read_file(project, {"path": "sub/file.txt"})
    assert result["content"] == "line1\nline2\nline3\n"
    assert not result["truncated"]


def test_read_file_line_range(project):
    result = agent.tool_read_file(project, {"path": "sub/file.txt", "start_line": 2, "end_line": 2})
    assert result["content"] == "line2\n"


def test_read_file_normalizes_crlf(tmp_path):
    root = str(tmp_path)
    with open(os.path.join(root, "crlf.txt"), "wb") as f:
        f.write(b"line1\r\nline2\r\n")
    result = agent.tool_read_file(root, {"path": "crlf.txt"})
    assert result["content"] == "line1\nline2\n"


def test_read_file_rejects_path_escape(project):
    with pytest.raises(agent.PathEscapeError):
        agent.tool_read_file(project, {"path": "../outside.txt"})


def test_list_directory_skips_ignored_dirs(project):
    result = agent.tool_list_directory(project, {"path": "."})
    assert "__pycache__/" not in result["entries"]
    assert "hello.py" in result["entries"]


def test_list_directory_recursive_finds_nested_file(project):
    result = agent.tool_list_directory(project, {"path": ".", "recursive": True})
    assert "sub/file.txt" in result["entries"]


def test_search_code_finds_match(project):
    result = agent.tool_search_code(project, {"pattern": "hello"})
    assert len(result["matches"]) >= 1


def test_search_code_rejects_invalid_regex(project):
    with pytest.raises(agent.ToolError):
        agent.tool_search_code(project, {"pattern": "("})


def test_prepare_write_file_never_touches_disk(project):
    proposal = agent.prepare_write_file(project, {"path": "new_file.py", "content": "x = 1\n"})
    assert not os.path.exists(os.path.join(project, "new_file.py"))
    assert proposal.old_content == ""
    assert proposal.new_content == "x = 1\n"


def test_prepare_write_file_captures_old_content_on_overwrite(project):
    proposal = agent.prepare_write_file(project, {"path": "hello.py", "content": "new content\n"})
    assert "hello world" in proposal.old_content
    # still untouched on disk until apply_write is called
    assert "hello world" in open(os.path.join(project, "hello.py")).read()


def test_apply_write_actually_writes(project):
    proposal = agent.prepare_write_file(project, {"path": "new_file.py", "content": "x = 1\n"})
    agent.apply_write(proposal)
    assert open(os.path.join(project, "new_file.py")).read() == "x = 1\n"


def test_prepare_edit_file_computes_new_content(project):
    proposal = agent.prepare_edit_file(
        project, {"path": "hello.py", "old_text": "hello world", "new_text": "goodbye world"}
    )
    assert "goodbye world" in proposal.new_content
    assert "hello world" in open(os.path.join(project, "hello.py")).read()  # untouched until applied


def test_prepare_edit_file_rejects_missing_text(project):
    with pytest.raises(agent.ToolError):
        agent.prepare_edit_file(project, {"path": "hello.py", "old_text": "does_not_exist", "new_text": "x"})


def test_prepare_edit_file_rejects_non_unique_match(project):
    dup = os.path.join(project, "dup.txt")
    with open(dup, "w", encoding="utf-8") as f:
        f.write("abc\nabc\n")
    with pytest.raises(agent.ToolError):
        agent.prepare_edit_file(project, {"path": "dup.txt", "old_text": "abc", "new_text": "xyz"})


def test_run_shell_command_executes_and_captures_output(project):
    result = agent.tool_run_shell_command(project, {"command": "echo hello-from-shell"})
    assert "hello-from-shell" in result["stdout"]
    assert result["exit_code"] == 0


def test_run_shell_command_rejects_cwd_path_escape(project):
    with pytest.raises(agent.PathEscapeError):
        agent.tool_run_shell_command(project, {"command": "echo x", "cwd": "../../"})
