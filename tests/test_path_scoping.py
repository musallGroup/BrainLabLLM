import os

import pytest

import agent


@pytest.fixture
def project(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file.txt").write_text("hi", encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize(
    "user_path",
    [
        "sub/file.txt",
        "sub\\file.txt",
        ".",
        "",
        "sub/",
        "sub/../sub/file.txt",
    ],
)
def test_valid_paths_resolve_inside_root(project, user_path):
    resolved = agent.resolve_scoped_path(project, user_path)
    assert os.path.commonpath([resolved, os.path.realpath(project)]) == os.path.realpath(project)


@pytest.mark.parametrize(
    "user_path",
    [
        "..\\..\\Windows\\System32",
        "../../etc/passwd",
        r"\\server\share\file.txt",
        "C:foo",
    ],
)
def test_traversal_and_unc_paths_are_rejected(project, user_path):
    with pytest.raises(agent.PathEscapeError):
        agent.resolve_scoped_path(project, user_path)


def test_absolute_path_outside_root_is_rejected(project, tmp_path_factory):
    outside = str(tmp_path_factory.mktemp("outside"))
    with pytest.raises(agent.PathEscapeError):
        agent.resolve_scoped_path(project, outside)


def test_absolute_path_inside_root_is_still_rejected(project):
    # Absolute paths are rejected outright, even ones that happen to resolve
    # inside root - the model never legitimately needs the real absolute path.
    inside_absolute = os.path.join(project, "sub", "file.txt")
    with pytest.raises(agent.PathEscapeError):
        agent.resolve_scoped_path(project, inside_absolute)


def test_symlink_escaping_root_is_rejected(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside_secret")
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link_path = os.path.join(project, "escape_link")
    try:
        os.symlink(str(outside), link_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation requires elevated privileges on this machine")

    with pytest.raises(agent.PathEscapeError):
        agent.resolve_scoped_path(project, "escape_link/secret.txt")
