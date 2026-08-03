import main


def test_group_items_empty_list():
    assert main.group_items([]) == []


def test_group_items_single_item():
    assert main.group_items(["a"]) == [["a"]]


def test_group_items_exact_multiple_of_size():
    items = ["a", "b", "c", "d", "e", "f"]
    assert main.group_items(items, size=6) == [["a", "b", "c", "d", "e", "f"]]


def test_group_items_one_more_than_size():
    items = ["a", "b", "c", "d", "e", "f", "g"]
    assert main.group_items(items, size=6) == [
        ["a", "b", "c", "d", "e", "f"],
        ["g"],
    ]


def test_group_items_custom_size():
    items = list(range(10))
    assert main.group_items(items, size=3) == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [9],
    ]


def test_group_items_preserves_order_and_content():
    items = ["chunk 1 summary", "chunk 2 summary", "chunk 3 summary"]
    groups = main.group_items(items, size=2)
    assert groups == [["chunk 1 summary", "chunk 2 summary"], ["chunk 3 summary"]]


def test_final_reduce_prompt_single_part_has_no_coverage_instruction():
    prompt = main._build_final_reduce_prompt(["some notes"])
    assert "some notes" in prompt
    assert "IMPORTANT" not in prompt
    assert "Key Points" in prompt
    assert main.SPEAKER_ATTRIBUTION_RULE in prompt


def test_final_reduce_prompt_multiple_parts_numbers_them_and_demands_coverage():
    parts = ["first part notes", "second part notes", "third part notes"]
    prompt = main._build_final_reduce_prompt(parts)
    assert "[Part 1 of 3]\nfirst part notes" in prompt
    assert "[Part 2 of 3]\nsecond part notes" in prompt
    assert "[Part 3 of 3]\nthird part notes" in prompt
    assert "IMPORTANT" in prompt
    assert "do not let the summary skew toward only" in prompt
    assert main.SPEAKER_ATTRIBUTION_RULE in prompt


def test_intermediate_reduce_prompt_preserves_speaker_attribution_instruction():
    prompt = main._build_intermediate_reduce_prompt(["Speaker 1: did X", "Speaker 2: did Y"])
    assert "Speaker 1: did X" in prompt
    assert "Speaker 2: did Y" in prompt
    assert "Keep speaker attributions" in prompt
    assert "do not compress further" in prompt
