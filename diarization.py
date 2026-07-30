"""Speaker diarization: "who spoke when", layered on top of (not replacing)
faster-whisper's own transcription. No tkinter import, no dependency on
main.py - same module shape as meeting.py/agent.py.

GPU-only by design (see docs/architecture.md#speaker-diarization): real-world
CPU performance for pyannote.audio is too unpredictable across unknown lab
hardware to offer as a safe default, unlike Whisper transcription itself
which already has a proven CPU fallback path.
"""

import os
import sys

# pyannote/speaker-diarization-community-1: CC-BY-4.0, single gated model
# (unlike speaker-diarization-3.1, which additionally depends on a
# separately-gated pyannote/segmentation-3.0 - one fewer thing to accept),
# better published accuracy, and explicitly designed for cleaner alignment
# with transcription timestamps - a better fit on every axis checked.
MODEL_CHECKPOINT = "pyannote/speaker-diarization-community-1"

_pipeline = None


def resolve_diarization_model_path():
    """Mirrors meeting.resolve_model_path(): a bundled local directory when
    frozen (packaged exe - no token needed, same as the Whisper model),
    otherwise the HF repo id plus a dev-only token from the environment
    (only needed for the one-time download that then gets bundled)."""
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "diarization_model")
        if os.path.isdir(bundled):
            return bundled, None
    return MODEL_CHECKPOINT, os.environ.get("HUGGINGFACE_TOKEN")


def _ensure_pipeline_loaded(on_status=None):
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    import torch
    from pyannote.audio import Pipeline

    if on_status:
        on_status("Loading speaker identification model...")

    checkpoint, token = resolve_diarization_model_path()
    pipeline = Pipeline.from_pretrained(checkpoint, token=token)
    if pipeline is None:
        raise RuntimeError(
            "Could not load the speaker identification model - if this is a dev environment, "
            "check that HUGGINGFACE_TOKEN is set and the gated model terms have been accepted."
        )
    pipeline.to(torch.device("cuda"))
    _pipeline = pipeline
    return _pipeline


def diarize(audio, sample_rate=16000, on_status=None):
    """audio: a mono float32 numpy array, OR a file path string (decoded via
    faster_whisper's own decode_audio - reused rather than adding a second
    audio-decoding dependency, and it sidesteps a real torchcodec/FFmpeg DLL
    loading issue found in this environment: pyannote's own file-path
    decoding depends on torchcodec, which fails to load its native library
    here, but pyannote explicitly supports - and its own error message
    recommends - passing pre-decoded audio as a tensor dict instead, which
    is what this always does regardless of input type.

    Returns friendly-labeled [(speaker, start, end), ...] turns, ready for
    assign_speakers_to_segments().
    """
    import torch
    from faster_whisper.audio import decode_audio

    if isinstance(audio, str):
        audio = decode_audio(audio, sampling_rate=sample_rate)

    pipeline = _ensure_pipeline_loaded(on_status)
    if on_status:
        on_status("Identifying speakers...")

    waveform = torch.from_numpy(audio).unsqueeze(0)  # (channel=1, time)
    output = pipeline({"waveform": waveform, "sample_rate": sample_rate})

    turns = [(speaker, turn.start, turn.end) for turn, speaker in output.speaker_diarization]
    return friendly_speaker_labels(turns)


def gpu_available():
    """Cheap check used to gate the "Identify speakers" UI control - imports
    torch lazily so machines that never touch this feature don't pay for it
    at startup."""
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def friendly_speaker_labels(diarization_turns):
    """Remaps pyannote's raw cluster labels (e.g. "SPEAKER_00") to
    human-friendly ones ("Speaker 1", "Speaker 2", ...), numbered in order of
    who spoke first - "Speaker 1" is whoever's first turn starts earliest."""
    first_seen = {}
    for speaker, start, _end in sorted(diarization_turns, key=lambda t: t[1]):
        if speaker not in first_seen:
            first_seen[speaker] = len(first_seen) + 1
    return [(f"Speaker {first_seen[speaker]}", start, end) for speaker, start, end in diarization_turns]


def _best_overlapping_speaker(seg_start, seg_end, diarization_turns, default="Unknown"):
    best_speaker = default
    best_overlap = 0.0
    for speaker, turn_start, turn_end in diarization_turns:
        overlap = min(seg_end, turn_end) - max(seg_start, turn_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker
    return best_speaker


def assign_speakers_to_segments(whisper_segments, diarization_turns):
    """whisper_segments: iterable of objects/tuples with start/end/text
    (accepts either faster-whisper's real Segment objects or plain
    (start, end, text) tuples, so this is testable without a real model).
    diarization_turns: list of (speaker_label, start, end) tuples.

    Returns a list of (speaker_label, text) tuples - consecutive segments
    from the same speaker are merged into one entry, so a speaker's several
    short Whisper segments don't each get their own repeated label.
    Segments with no overlapping diarization turn (silence, edge uncertainty)
    fall back to "Unknown" rather than a guess.
    """
    results = []
    for seg in whisper_segments:
        start = seg.start if hasattr(seg, "start") else seg[0]
        end = seg.end if hasattr(seg, "end") else seg[1]
        text = (seg.text if hasattr(seg, "text") else seg[2]).strip()
        if not text:
            continue

        speaker = _best_overlapping_speaker(start, end, diarization_turns)

        if results and results[-1][0] == speaker:
            results[-1] = (speaker, results[-1][1] + " " + text)
        else:
            results.append((speaker, text))
    return results


def format_speaker_transcript(labeled_segments):
    """Renders assign_speakers_to_segments' output as the transcript string
    shown in the UI and fed to summarization - "Speaker N: ..." per line,
    parseable back out by main.py for per-speaker coloring."""
    return "\n".join(f"{speaker}: {text}" for speaker, text in labeled_segments)
