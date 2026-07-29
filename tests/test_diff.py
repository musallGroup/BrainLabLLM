import agent


def test_diff_contains_expected_line_kinds():
    old = "line1\nline2\nline3\n"
    new = "line1\nlineTWO\nline3\nline4\n"
    diff = agent.compute_diff(old, new, "test.txt")
    tags = [t for t, _ in diff]

    assert "header" in tags
    assert any(t == "add" and "lineTWO" in l for t, l in diff)
    assert any(t == "remove" and "line2" in l for t, l in diff)
    assert any(t == "context" and "line1" in l for t, l in diff)
    assert any(t == "add" and "line4" in l for t, l in diff)


def test_identical_content_produces_empty_diff():
    assert agent.compute_diff("abc\n", "abc\n", "x.txt") == []


def test_new_file_diff_shows_all_additions():
    diff = agent.compute_diff("", "brand new content\n", "new.py")
    assert any(t == "add" and "brand new content" in l for t, l in diff)


def test_large_diff_is_truncated():
    big_old = "\n".join(f"old{i}" for i in range(1000)) + "\n"
    big_new = "\n".join(f"new{i}" for i in range(1000)) + "\n"
    diff = agent.compute_diff(big_old, big_new, "big.txt")
    assert len(diff) <= agent.MAX_DIFF_LINES + 1
    assert any("truncated" in l for _, l in diff)
