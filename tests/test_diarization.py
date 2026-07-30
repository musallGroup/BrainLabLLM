import diarization


def test_friendly_labels_numbered_by_who_spoke_first():
    turns = [
        ("SPEAKER_01", 5.0, 8.0),
        ("SPEAKER_00", 0.0, 4.0),
        ("SPEAKER_01", 8.5, 10.0),
    ]
    result = diarization.friendly_speaker_labels(turns)
    # SPEAKER_00's first turn starts at 0.0 (earliest) -> "Speaker 1"
    # SPEAKER_01's first turn starts at 5.0 -> "Speaker 2"
    assert result[0] == ("Speaker 2", 5.0, 8.0)
    assert result[1] == ("Speaker 1", 0.0, 4.0)
    assert result[2] == ("Speaker 2", 8.5, 10.0)


def test_friendly_labels_handles_three_speakers():
    turns = [("SPEAKER_02", 0.0, 1.0), ("SPEAKER_00", 1.0, 2.0), ("SPEAKER_01", 2.0, 3.0)]
    result = diarization.friendly_speaker_labels(turns)
    assert [r[0] for r in result] == ["Speaker 1", "Speaker 2", "Speaker 3"]


def test_assign_speakers_basic_two_speaker_alternation():
    segments = [
        (0.0, 2.0, "Hello there."),
        (2.5, 4.0, "Hi, how are you?"),
        (4.5, 6.0, "I'm doing well."),
    ]
    turns = [
        ("Speaker 1", 0.0, 2.2),
        ("Speaker 2", 2.3, 4.2),
        ("Speaker 1", 4.3, 6.2),
    ]
    result = diarization.assign_speakers_to_segments(segments, turns)
    assert result == [
        ("Speaker 1", "Hello there."),
        ("Speaker 2", "Hi, how are you?"),
        ("Speaker 1", "I'm doing well."),
    ]


def test_assign_speakers_merges_consecutive_same_speaker():
    segments = [
        (0.0, 1.0, "First sentence."),
        (1.1, 2.0, "Second sentence, same speaker."),
        (2.1, 3.0, "Third, still same speaker."),
    ]
    turns = [("Speaker 1", 0.0, 3.5)]
    result = diarization.assign_speakers_to_segments(segments, turns)
    assert result == [("Speaker 1", "First sentence. Second sentence, same speaker. Third, still same speaker.")]


def test_assign_speakers_no_overlap_falls_back_to_unknown():
    segments = [(10.0, 11.0, "Said during silence in diarization")]
    turns = [("Speaker 1", 0.0, 1.0)]
    result = diarization.assign_speakers_to_segments(segments, turns)
    assert result == [("Unknown", "Said during silence in diarization")]


def test_assign_speakers_picks_majority_overlap_not_first_match():
    # Segment mostly overlaps Speaker 2's turn, only a sliver touches Speaker 1
    segments = [(1.9, 4.0, "Mostly speaker 2's turn")]
    turns = [("Speaker 1", 0.0, 2.0), ("Speaker 2", 2.0, 5.0)]
    result = diarization.assign_speakers_to_segments(segments, turns)
    assert result == [("Speaker 2", "Mostly speaker 2's turn")]


def test_assign_speakers_empty_text_segments_are_skipped():
    segments = [(0.0, 1.0, "   "), (1.0, 2.0, "Real text")]
    turns = [("Speaker 1", 0.0, 2.0)]
    result = diarization.assign_speakers_to_segments(segments, turns)
    assert result == [("Speaker 1", "Real text")]


def test_assign_speakers_accepts_object_style_segments():
    class FakeSegment:
        def __init__(self, start, end, text):
            self.start = start
            self.end = end
            self.text = text

    segments = [FakeSegment(0.0, 1.0, "Object-style segment")]
    turns = [("Speaker 1", 0.0, 1.0)]
    result = diarization.assign_speakers_to_segments(segments, turns)
    assert result == [("Speaker 1", "Object-style segment")]


def test_format_speaker_transcript():
    labeled = [("Speaker 1", "Hello."), ("Speaker 2", "Hi there.")]
    assert diarization.format_speaker_transcript(labeled) == "Speaker 1: Hello.\nSpeaker 2: Hi there."


def test_format_speaker_transcript_empty():
    assert diarization.format_speaker_transcript([]) == ""


def test_gpu_available_returns_bool():
    # Just confirm it doesn't raise and returns a real bool, regardless of
    # what hardware the test happens to run on.
    assert isinstance(diarization.gpu_available(), bool)
