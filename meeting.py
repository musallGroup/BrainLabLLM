import os
import sys
import threading
import time

import numpy as np
import queue
import sounddevice as sd
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

TARGET_RATE = 16000


def resolve_model_path(model_size):
    """When packaged (frozen exe), use the bundled local model directory so
    no internet access is needed on first run. In dev mode, fall back to the
    Hugging Face Hub model name, which faster-whisper downloads on first use.
    """
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "whisper_model")
        if os.path.isdir(bundled):
            return bundled
    return model_size


def find_input_device(name_substring=None):
    """Find an input device index, preferring one matching name_substring,
    falling back to the system default, then to the first available input.

    Device indices shift when devices are plugged/unplugged, so callers
    should look up by name rather than hardcoding an index.
    """
    devices = sd.query_devices()
    if name_substring:
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and name_substring.lower() in d["name"].lower():
                return i
    default_in = sd.default.device[0]
    if default_in is not None and default_in >= 0:
        return default_in
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            return i
    raise RuntimeError("No audio input device found")


def list_input_devices():
    """Returns [(index, name), ...] for every device with at least one input channel."""
    return [
        (i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0
    ]


def test_microphone(device, duration=2.0):
    """Records briefly from device and returns (peak_amplitude, mean_rms).

    Lightweight sanity check - no Whisper model needed - so users can
    confirm their mic actually picks up sound before recording a real
    meeting. A muted/disconnected mic reads back as ~0.0 with no error,
    which is exactly the confusing failure mode this is meant to catch.
    """
    recorder = AudioRecorder(device)
    recorder.start()
    blocks = []
    start = time.time()
    while time.time() - start < duration:
        block = recorder.read_block(timeout=0.5)
        if block is not None:
            blocks.append(block)
    recorder.stop()
    if not blocks:
        return 0.0, 0.0
    audio = np.concatenate(blocks)
    peak = float(np.abs(audio).max())
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    return peak, rms


class AudioRecorder:
    """Captures raw audio from an input device into a queue.

    The sounddevice callback stays trivial (just enqueues a copy) since it
    runs on PortAudio's own realtime thread - no math or processing there.
    """

    def __init__(self, device, block_duration=0.1):
        self.device = device
        dev_info = sd.query_devices(device)
        self.native_rate = int(dev_info["default_samplerate"])
        self.channels = dev_info["max_input_channels"]
        self.block_duration = block_duration
        self.blocksize = int(self.native_rate * block_duration)
        self.queue = queue.Queue()
        self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            print("STREAM_STATUS:", status)
        self.queue.put(indata.copy())

    def start(self):
        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.native_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def read_block(self, timeout=None):
        """Returns the next block as resampled mono float32 @ TARGET_RATE, or None on timeout."""
        try:
            block = self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
        mono = block.mean(axis=1) if block.ndim > 1 and block.shape[1] > 1 else block.flatten()
        if self.native_rate != TARGET_RATE:
            mono = resample_poly(mono, TARGET_RATE, self.native_rate).astype(np.float32)
        return mono.astype(np.float32)


class MeetingSession:
    """Records audio continuously, then transcribes the whole recording in
    one pass once Stop is called - using faster-whisper's own built-in VAD
    filtering (vad_filter=True, backed by Silero VAD internally) to handle
    segmentation, rather than a hand-rolled energy-threshold segmenter.

    This trades away incremental/live transcript updates during recording
    for much better reliability: continuous or fast speech doesn't get
    fragmented mid-sentence by an external VAD making live guesses, since
    the whole recording is transcribed with full context in one call.

    A recording_token (mirroring ChatApp's generation_token pattern)
    distinguishes each session so a quick Stop->Start can't let a stale
    callback from a previous session land in the new one.
    """

    def __init__(
        self,
        root,
        device=None,
        model_size="medium",
        device_preference="auto",
        on_transcript=None,
        on_status=None,
        on_device_ready=None,
        on_recording_started=None,
        on_recording_failed=None,
        on_error=None,
    ):
        self.root = root
        self.device = device if device is not None else find_input_device()
        self.model_size = model_size
        self.device_preference = device_preference
        self.on_transcript = on_transcript or (lambda text: None)
        self.on_status = on_status or (lambda msg: None)
        self.on_device_ready = on_device_ready or (lambda device_used: None)
        self.on_recording_started = on_recording_started or (lambda: None)
        self.on_recording_failed = on_recording_failed or (lambda: None)
        # Distinct from on_status: a transcription failure needs the caller
        # to also unstick any "busy" UI state, not just display a message -
        # on_status alone can't tell the caller the operation is actually
        # over (see main.py's _on_meeting_error).
        self.on_error = on_error or (lambda msg: None)

        self.recording_token = 0
        self.recorder = None
        self._blocks = []
        self._capture_thread = None
        self._stop_capture = threading.Event()

        self.model = None
        self.device_used = None

    def _ensure_model_loaded(self):
        if self.model is not None:
            return
        model_path = resolve_model_path(self.model_size)
        if self.device_preference == "cpu":
            self.model = WhisperModel(model_path, device="cpu", compute_type="int8")
            self.device_used = "cpu"
            return

        # GPU init is attempted on its own thread with a timeout: on unknown
        # hardware/driver combinations, a bad CUDA setup can hang rather than
        # raise a clean exception, and a plain try/except can't catch a hang.
        # The daemon thread is left to die on its own if it never returns.
        result = {}

        def try_gpu():
            try:
                model = WhisperModel(model_path, device="cuda", compute_type="float16")
                warmup = np.zeros(TARGET_RATE // 2, dtype=np.float32)
                list(model.transcribe(warmup)[0])
                result["model"] = model
            except Exception as exc:
                result["error"] = exc

        gpu_thread = threading.Thread(target=try_gpu, daemon=True)
        gpu_thread.start()
        gpu_thread.join(timeout=30)

        if gpu_thread.is_alive():
            error_desc = "GPU initialization timed out"
        elif "model" in result:
            self.model = result["model"]
            self.device_used = "cuda"
            return
        else:
            error_desc = repr(result.get("error"))

        if self.device_preference == "cuda":
            self.on_status(f"GPU required but unavailable ({error_desc})")
            raise RuntimeError(error_desc)
        self.on_status("GPU not available, using CPU (slower)")
        self.model = WhisperModel(model_path, device="cpu", compute_type="int8")
        self.device_used = "cpu"

    def start(self):
        self.recording_token += 1
        token = self.recording_token
        self._stop_capture.clear()
        self._blocks = []
        self.recorder = AudioRecorder(self.device)

        def init_and_capture():
            self.root.after(0, self._handle_status, token, "Loading model...")
            try:
                self._ensure_model_loaded()
            except Exception as exc:
                self.root.after(0, self._handle_status, token, f"Failed to load transcription model: {exc}")
                self.root.after(0, self._handle_failed, token)
                return
            if token != self.recording_token:
                return
            self.root.after(0, self._handle_status, token, f"Recording (model ready on {self.device_used})")
            self.root.after(0, self.on_device_ready, self.device_used)
            try:
                self.recorder.start()
            except Exception as exc:
                self.root.after(0, self._handle_status, token, f"Failed to open microphone: {exc}")
                self.root.after(0, self._handle_failed, token)
                return
            self.root.after(0, self._handle_started, token)
            self._capture_loop(token)

        self._capture_thread = threading.Thread(target=init_and_capture, daemon=True)
        self._capture_thread.start()

    def _capture_loop(self, token):
        while not self._stop_capture.is_set() and token == self.recording_token:
            block = self.recorder.read_block(timeout=0.5)
            if block is None:
                continue
            self._blocks.append(block)

    def stop(self):
        """Stops capture and kicks off transcription of the full recording.

        Blocks briefly (well under a second) until the capture thread has
        exited, so a subsequent start() never races with left-over state.
        """
        self._stop_capture.set()
        token = self.recording_token
        if self.recorder is not None:
            self.recorder.stop()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=5)

        blocks, self._blocks = self._blocks, []
        if not blocks:
            self._handle_status(token, "No audio captured")
            self._handle_transcript(token, "")
            return

        audio = np.concatenate(blocks)

        def transcribe():
            self.root.after(0, self._handle_status, token, "Transcribing...")
            try:
                self._ensure_model_loaded()
            except Exception as exc:
                self.root.after(0, self._handle_error, token, f"Failed to load transcription model: {exc}")
                return
            if token != self.recording_token:
                return
            try:
                segments, info = self.model.transcribe(audio, beam_size=5, vad_filter=True)
                text = " ".join(s.text.strip() for s in segments)
            except Exception as exc:
                self.root.after(0, self._handle_error, token, f"Transcription failed: {exc}")
                return
            self.root.after(0, self._handle_transcript, token, text)
            self.root.after(0, self._handle_status, token, "Done")

        threading.Thread(target=transcribe, daemon=True).start()

    def transcribe_file(self, path):
        """Transcribes an existing audio/video file rather than a live
        recording - reuses the same model (loading it with the same
        GPU/CPU fallback if not already loaded) and the same
        on_transcript/on_status/on_error callbacks as live recording, so a
        caller that already has a MeetingSession wired up needs no separate
        UI-update path for this.

        faster-whisper decodes the file itself (via PyAV, so effectively
        anything ffmpeg understands - wav/mp3/m4a/etc, even video files)
        given a path directly, unlike the live-recording path which has to
        manually capture and resample raw audio.
        """
        self.recording_token += 1
        token = self.recording_token
        filename = os.path.basename(path)

        def transcribe():
            self.root.after(0, self._handle_status, token, "Loading model...")
            try:
                self._ensure_model_loaded()
            except Exception as exc:
                self.root.after(0, self._handle_error, token, f"Failed to load transcription model: {exc}")
                return
            if token != self.recording_token:
                return
            self.root.after(0, self._handle_status, token, f"Transcribing {filename}...")
            try:
                segments, info = self.model.transcribe(path, beam_size=5, vad_filter=True)
                text = " ".join(s.text.strip() for s in segments)
            except Exception as exc:
                self.root.after(0, self._handle_error, token, f"Transcription failed: {exc}")
                return
            if token != self.recording_token:
                return
            self.root.after(0, self._handle_transcript, token, text)
            self.root.after(0, self._handle_status, token, "Done")

        threading.Thread(target=transcribe, daemon=True).start()
        return token

    def _handle_status(self, token, msg):
        if token != self.recording_token:
            return
        self.on_status(msg)

    def _handle_started(self, token):
        if token != self.recording_token:
            return
        self.on_recording_started()

    def _handle_failed(self, token):
        if token != self.recording_token:
            return
        self.on_recording_failed()

    def _handle_transcript(self, token, text):
        if token != self.recording_token:
            return
        self.on_transcript(text)

    def _handle_error(self, token, msg):
        if token != self.recording_token:
            return
        self.on_error(msg)


def _console_test(device=None, duration=30):
    """Standalone record-then-transcribe test, no Tkinter involved."""
    device = device if device is not None else find_input_device("webcam")
    print("Loading model...")
    model = WhisperModel("medium", device="cuda", compute_type="float16")
    print("MODEL_READY")

    recorder = AudioRecorder(device)
    recorder.start()
    print(f"RECORDING_STARTED for {duration}s")
    blocks = []
    start = time.time()
    while time.time() - start < duration:
        block = recorder.read_block(timeout=0.5)
        if block is not None:
            blocks.append(block)
    recorder.stop()
    print("RECORDING_STOPPED, transcribing...")

    audio = np.concatenate(blocks)
    segments, info = model.transcribe(audio, beam_size=5, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments)
    print(f"TRANSCRIPT: {text!r}")


if __name__ == "__main__":
    _console_test()
