"""
OpenDAW — single-file version
A lightweight multi-track playback & mixing DAW built with Python and Tkinter.

Install dependencies first:
    pip install numpy sounddevice soundfile
    pip install mido python-rtmidi   # optional: MIDI device listing

On Linux you may also need:
    sudo apt-get install libportaudio2

Run:
    python opendaw.py
"""

import os
import json
import time
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

try:
    import mido
except ImportError:
    mido = None


# ======================================================================
# App / theme constants
# ======================================================================
APP_NAME = "OpenDAW"

BG = "#1e1e1e"          # main dark grey background
BG_PANEL = "#2a2a2a"    # toolbar / transport / left panel background
BG_TRACK = "#242424"    # track row background
FG = "#e0e0e0"          # light grey text
FG_DIM = "#888888"
ACCENT = "#00d9ff"      # neon blue
ACCENT_DIM = "#0090b0"
DIVIDER = "#0090b0"     # partition line color
GRID_LINE = "#3a3a3a"   # subtle timeline gridlines
RECORD_RED = "#ff3333"
RECORD_RED_DIM = "#661111"

WAVEFORM_HEIGHT = 50
TIMELINE_WIDTH = 600          # shared pixel width for the whole timeline
RULER_HEIGHT = 24
MIN_TIMELINE_SECONDS = 10     # never zoom in past this, even for short clips
LEFT_PANEL_WIDTH = 170
HANDLE_TOLERANCE = 6          # pixels of "grab distance" around a trim handle
TICK_INTERVALS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]

# Piano roll
PIANO_KEY_HEIGHT = 18
PIANO_KEY_WIDTH = 55
PIANO_NOTE_WIDTH = 70
PIANO_OCTAVES = 4
PIANO_LOW_MIDI = 48  # C3
PIANO_BEATS = 32

# Drum machine
DRUM_STEPS = 16
DRUM_ROWS = ["Kick", "Snare", "Closed Hat", "Open Hat", "Clap"]
AUTOSAVE_INTERVAL_MS = 30000
MAX_UNDO_HISTORY = 100

TRACK_COLORS = [
    "#00d9ff",  # cyan
    "#ff4d6d",  # red/pink
    "#9b5de5",  # purple
    "#00c853",  # green
    "#ffab00",  # amber
    "#00b8d4",  # teal
    "#f15bb5",  # magenta
    "#8bc34a",  # lime
]


# ======================================================================
# Track
# ======================================================================
class Track:
    """A single track: loaded audio data plus mixer state (volume, mute, solo, trim)."""

    def __init__(self, file_path: str, name: str = None, color: str = None):
        self.file_path = file_path
        self.name = name or os.path.basename(file_path)
        self.color = color or TRACK_COLORS[0]

        # Load audio as float32, always as 2D (frames, channels)
        data, sample_rate = sf.read(file_path, dtype="float32", always_2d=True)

        self.data = data                # shape: (num_frames, num_channels)
        self.sample_rate = sample_rate

        # Mixer state
        self.volume = 1.0               # 0.0 - 1.0+ (gain multiplier)
        self.muted = False
        self.solo = False
        self.pan = 0.0

        # Timeline placement in output/engine frames.
        self.start_frame = 0

        # Trim state — in this track's OWN sample frames (not engine frames)
        self.trim_start = 0
        self.trim_end = self.num_frames

        # Clip fades, in seconds, applied inside the trimmed region.
        self.fade_in = 0.0
        self.fade_out = 0.0

        # Per-track effects. Values are intentionally simple so the DAW
        # remains lightweight and dependency-free beyond numpy/soundfile.
        self.effects = {
            "gain": 0.0,          # dB
            "delay": 0.0,        # wet 0..1
            "delay_time": 0.25,  # seconds
            "reverb": 0.0,       # wet 0..1
            "distortion": 0.0,   # 0..1
            "compressor": 0.0,   # 0..1
            "lowpass": 20000.0,  # Hz
            "highpass": 20.0,    # Hz
        }
        self._processed_cache = None

    @property
    def num_frames(self) -> int:
        return self.data.shape[0]

    @property
    def channels(self) -> int:
        return self.data.shape[1]

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate == 0:
            return 0.0
        return self.num_frames / self.sample_rate

    @property
    def trimmed_frames(self) -> int:
        return max(0, self.trim_end - self.trim_start)

    def set_trim(self, start, end):
        start = max(0, min(int(start), self.num_frames))
        end = max(0, min(int(end), self.num_frames))
        if end <= start:
            end = min(self.num_frames, start + 1)
        self.trim_start = start
        self.trim_end = end

    def get_waveform_peaks(self, num_buckets: int):
        """
        Downsample the FULL track (ignoring trim) to `num_buckets` (min, max)
        pairs for fast waveform drawing, regardless of file length.
        """
        num_buckets = max(1, num_buckets)
        mono = self.data.mean(axis=1) if self.channels > 1 else self.data[:, 0]
        n = len(mono)

        if n == 0:
            return np.zeros(num_buckets), np.zeros(num_buckets)

        bucket_size = max(1, n // num_buckets)
        usable = bucket_size * num_buckets

        if usable == 0:
            padded = np.zeros(num_buckets)
            padded[:n] = mono
            return padded, padded

        trimmed = mono[:usable].reshape(num_buckets, bucket_size)
        mins = trimmed.min(axis=1)
        maxs = trimmed.max(axis=1)
        return mins, maxs

    def invalidate_effect_cache(self):
        self._processed_cache = None

    def get_processed_data(self):
        """Return audio after the current track effects are applied."""
        if self._processed_cache is not None:
            return self._processed_cache

        data = self.data.astype(np.float32, copy=True)
        if len(data) == 0:
            self._processed_cache = data
            return data

        # Gain
        gain_db = float(self.effects.get("gain", 0.0))
        if abs(gain_db) > 1e-6:
            data *= float(10.0 ** (gain_db / 20.0))

        # High-pass / low-pass: lightweight one-pole filters.
        sr = float(self.sample_rate or 44100)
        hp = max(20.0, min(float(self.effects.get("highpass", 20.0)), sr * 0.45))
        lp = max(hp + 1.0, min(float(self.effects.get("lowpass", 20000.0)), sr * 0.49))

        if hp > 20.1:
            rc = 1.0 / (2.0 * np.pi * hp)
            alpha = rc / (rc + 1.0 / sr)
            prev_x = np.zeros(data.shape[1], dtype=np.float32)
            prev_y = np.zeros(data.shape[1], dtype=np.float32)
            for i in range(len(data)):
                x = data[i].copy()
                y = alpha * (prev_y + x - prev_x)
                data[i] = y
                prev_x = x
                prev_y = y

        if lp < sr * 0.49:
            rc = 1.0 / (2.0 * np.pi * lp)
            alpha = (1.0 / sr) / (rc + 1.0 / sr)
            prev = data[0].copy()
            for i in range(1, len(data)):
                prev = prev + alpha * (data[i] - prev)
                data[i] = prev

        # Distortion / soft clipping
        drive = max(0.0, min(1.0, float(self.effects.get("distortion", 0.0))))
        if drive > 0.001:
            amount = 1.0 + drive * 14.0
            wet = 0.15 + drive * 0.75
            distorted = np.tanh(data * amount)
            data = data * (1.0 - wet) + distorted * wet

        # Simple compressor with adjustable strength.
        comp = max(0.0, min(1.0, float(self.effects.get("compressor", 0.0))))
        if comp > 0.001:
            threshold = 0.55 - comp * 0.30
            ratio = 2.0 + comp * 8.0
            magnitude = np.abs(data)
            over = magnitude > threshold
            gain = np.ones_like(magnitude)
            gain[over] = (threshold + (magnitude[over] - threshold) / ratio) / np.maximum(magnitude[over], 1e-8)
            data *= gain

        # Delay
        delay_wet = max(0.0, min(1.0, float(self.effects.get("delay", 0.0))))
        if delay_wet > 0.001:
            delay_samples = max(1, int(float(self.effects.get("delay_time", 0.25)) * sr))
            delayed = np.zeros_like(data)
            if delay_samples < len(data):
                delayed[delay_samples:] = data[:-delay_samples]
            data = data * (1.0 - delay_wet) + delayed * delay_wet

        # Small synthetic room reverb using several short taps.
        reverb_wet = max(0.0, min(1.0, float(self.effects.get("reverb", 0.0))))
        if reverb_wet > 0.001:
            wet = np.zeros_like(data)
            taps = [(0.031, 0.32), (0.047, 0.22), (0.071, 0.16), (0.113, 0.11)]
            for delay_sec, level in taps:
                d = max(1, int(delay_sec * sr))
                if d < len(data):
                    wet[d:] += data[:-d] * level
            data = data * (1.0 - reverb_wet) + wet * reverb_wet

        np.clip(data, -1.0, 1.0, out=data)
        self._processed_cache = data.astype(np.float32, copy=False)
        return self._processed_cache

    def __repr__(self):
        return f"<Track '{self.name}' {self.duration_seconds:.1f}s vol={self.volume:.2f}>"


# ======================================================================
# AudioEngine
# ======================================================================
class AudioEngine:
    """
    Real-time multi-track mixing & playback engine.

    Tracks can have different sample rates / channel counts, and each track
    can be trimmed to a sub-range; this engine normalizes everything to a
    common output sample rate/channel count at playback time.
    """

    def __init__(self, sample_rate: int = 44100, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels

        self.tracks = []           # list[Track]
        self.position = 0          # playhead, in output-rate frames
        self.playing = False
        self.master_volume = 1.0

        self._stream = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------
    # Track management
    # ------------------------------------------------------------
    def add_track(self, track):
        with self._lock:
            self.tracks.append(track)

    def remove_track(self, track):
        with self._lock:
            if track in self.tracks:
                self.tracks.remove(track)

    def total_frames(self) -> int:
        """Length of the whole timeline, in output-rate frames (respects trim)."""
        with self._lock:
            if not self.tracks:
                return 0
            return max(t.start_frame + self._resampled_length(t) for t in self.tracks)

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------
    def _resampled_length(self, track) -> int:
        frames = track.trimmed_frames
        if track.sample_rate == self.sample_rate:
            return frames
        ratio = self.sample_rate / track.sample_rate
        return int(round(frames * ratio))

    def _track_slice(self, track, start: int, end: int) -> np.ndarray:
        """Return the portion of a track overlapping the requested timeline range."""
        n = end - start
        out = np.zeros((n, self.channels), dtype="float32")

        length = self._resampled_length(track)
        clip_start = track.start_frame
        clip_end = clip_start + length
        overlap_start = max(start, clip_start)
        overlap_end = min(end, clip_end)
        if overlap_start >= overlap_end:
            return out

        local_start = overlap_start - clip_start
        avail = overlap_end - overlap_start
        dest_start = overlap_start - start

        processed = track.get_processed_data()
        if track.sample_rate == self.sample_rate:
            src_start = track.trim_start + local_start
            chunk = processed[src_start:src_start + avail]
        else:
            ratio = track.sample_rate / self.sample_rate
            src_start = track.trim_start + local_start * ratio
            src_positions = src_start + np.arange(avail) * ratio
            src_indices = np.clip(src_positions, track.trim_start, max(track.trim_end - 1, track.trim_start)).astype(np.int64)
            chunk = processed[src_indices]

        if track.channels == self.channels:
            matched = chunk
        elif track.channels == 1 and self.channels == 2:
            matched = np.repeat(chunk, 2, axis=1)
        elif track.channels == 2 and self.channels == 1:
            matched = chunk.mean(axis=1, keepdims=True)
        else:
            matched = np.zeros((chunk.shape[0], self.channels), dtype="float32")
            common = min(track.channels, self.channels)
            matched[:, :common] = chunk[:, :common]

        if track.fade_in > 0 or track.fade_out > 0:
            local_positions = np.arange(avail, dtype=np.float32) + local_start
            fade_gain = np.ones(avail, dtype=np.float32)
            if track.fade_in > 0:
                fade_frames = max(1, int(track.fade_in * self.sample_rate))
                fade_gain *= np.minimum(1.0, local_positions / fade_frames)
            if track.fade_out > 0:
                fade_frames = max(1, int(track.fade_out * self.sample_rate))
                remaining = self._resampled_length(track) - local_positions
                fade_gain *= np.minimum(1.0, remaining / fade_frames)
            matched = matched * fade_gain[:, None]

        out[dest_start:dest_start + avail] = matched
        return out

    def _mix_range(self, start, end):
        """Mix one timeline range into an array."""
        n = max(0, end - start)
        mix = np.zeros((n, self.channels), dtype="float32")
        any_solo = any(t.solo for t in self.tracks)
        for t in self.tracks:
            if t.muted:
                continue
            if any_solo and not t.solo:
                continue
            mix += self._track_slice(t, start, end) * t.volume
        mix *= self.master_volume
        np.clip(mix, -1.0, 1.0, out=mix)
        return mix

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if self.loop_enabled:
                total_now = max((t.start_frame + self._resampled_length(t) for t in self.tracks), default=0)
                if total_now <= 0:
                    self.loop_enabled = False
                else:
                    self.loop_start = max(0, min(int(self.loop_start), total_now - 1))
                    self.loop_end = max(self.loop_start + 1, min(int(self.loop_end or total_now), total_now))
            if not self.loop_enabled or self.loop_end <= self.loop_start:
                start = self.position
                end = start + frames
                mix = self._mix_range(start, end)
                outdata[:] = mix
                self.position = end
                total = max((t.start_frame + self._resampled_length(t) for t in self.tracks), default=0)
                reached_end = total and self.position >= total
            else:
                loop_start = max(0, int(self.loop_start))
                loop_end = max(loop_start + 1, int(self.loop_end))
                remaining = frames
                write_pos = 0
                while remaining > 0:
                    if self.position < loop_start or self.position >= loop_end:
                        self.position = loop_start
                    take = min(remaining, loop_end - self.position)
                    chunk = self._mix_range(self.position, self.position + take)
                    outdata[write_pos:write_pos + take] = chunk
                    self.position += take
                    write_pos += take
                    remaining -= take
                    if self.position >= loop_end:
                        self.position = loop_start
                reached_end = False

        if reached_end:
            self.playing = False
            raise sd.CallbackStop()

    # ------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------
    def play(self):
        if self.playing or not self.tracks:
            return

        if self.position >= self.total_frames():
            self.position = 0

        self.playing = True
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=self._callback,
            finished_callback=self._on_finished,
        )
        self._stream.start()

    def pause(self):
        if self._stream is not None and self.playing:
            self._stream.stop()
            self.playing = False

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.playing = False
        self.position = 0

    def seek(self, frame: int):
        with self._lock:
            self.position = max(0, frame)

    def _on_finished(self):
        self.playing = False

    # ------------------------------------------------------------
    # Offline rendering (for export/bounce)
    # ------------------------------------------------------------
    def render_mix(self) -> np.ndarray:
        """Render the full current mix (respecting volume/mute/solo/trim) to an array."""
        total = self.total_frames()
        if total == 0:
            return np.zeros((0, self.channels), dtype="float32")

        mix = np.zeros((total, self.channels), dtype="float32")
        any_solo = any(t.solo for t in self.tracks)

        chunk_size = 44100
        pos = 0
        while pos < total:
            end = min(pos + chunk_size, total)
            for t in self.tracks:
                if t.muted:
                    continue
                if any_solo and not t.solo:
                    continue
                track_audio = self._track_slice(t, pos, end) * t.volume
                if self.channels >= 2:
                    pan = max(-1.0, min(1.0, float(getattr(t, "pan", 0.0))))
                    angle = (pan + 1.0) * np.pi / 4.0
                    track_audio[:, 0] *= np.cos(angle)
                    track_audio[:, 1] *= np.sin(angle)
                mix[pos:end] += track_audio
            pos = end

        mix *= self.master_volume
        np.clip(mix, -1.0, 1.0, out=mix)
        return mix

    def export_mix(self, file_path: str):
        mix = self.render_mix()
        sf.write(file_path, mix, self.sample_rate)


# ======================================================================
# GUI
# ======================================================================
class DawApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("900x600")
        self.root.minsize(700, 450)
        self.root.configure(bg=BG)

        self._apply_dark_theme()

        self.engine = AudioEngine()
        self.track_canvases = {}   # Track -> tk.Canvas
        self.track_rows = {}       # Track -> row Frame
        self.track_name_labels = {}
        self._drag_state = {"track": None, "canvas": None, "handle": None}
        self.selected_track = None

        # timeline scale, recomputed as tracks are added/removed
        self.pixels_per_second = TIMELINE_WIDTH / MIN_TIMELINE_SECONDS
        self.timeline_basis_seconds = MIN_TIMELINE_SECONDS

        # recording state
        self.recording = False
        self._record_stream = None
        self._record_buffers = []
        self.record_start_frame = 0
        self.input_peak = 0.0
        self.input_device_indices = []
        self.input_device_names = []
        self.midi_input_name = "No MIDI Input"
        self.midi_input_names = []

        # Undo / redo history
        self._undo_stack = []
        self._redo_stack = []
        self._restoring_history = False
        self._last_history_signature = None

        self.markers = []  # {frame, name}
        self.autosave_enabled = True
        self.project_path = None

        # Loop / cycle state (engine frames)
        self.loop_enabled = False
        self.loop_start = 0
        self.loop_end = 0

        # Piano roll state
        self.piano_roll_visible = False
        self.piano_notes = set()  # (midi_note, beat)
        self.piano_instrument = tk.StringVar(value="Piano")
        self.drum_machine_visible = False
        self.drum_pattern = {row: set() for row in DRUM_ROWS}
        self._build_top_bar()
        self._build_divider(horizontal=True)
        self._build_main_area()
        self._build_divider(horizontal=True)
        self._build_transport()
        self._bind_shortcuts()

        self._draw_ruler()
        self._update_loop()
        self._update_input_meter()
        self._update_history_buttons()
        self._update_loop_button()
        self._last_history_signature = self._state_signature(self._capture_state())
        self.root.after(AUTOSAVE_INTERVAL_MS, self._autosave_tick)

    # ------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------
    def _apply_dark_theme(self):
        style = ttk.Style()
        style.theme_use("clam")  # required so custom colors actually show on Windows

        style.configure(".", background=BG, foreground=FG)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)

        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG)

        style.configure("Track.TFrame", background=BG_TRACK,
                         bordercolor=ACCENT_DIM, relief="solid", borderwidth=1)
        style.configure("Track.TLabel", background=BG_TRACK, foreground=FG)

        style.configure("TButton", background=BG_PANEL, foreground=ACCENT,
                         borderwidth=1, focusthickness=0, padding=6)
        style.map("TButton",
                  background=[("active", ACCENT_DIM)],
                  foreground=[("active", "#ffffff")])

        style.configure("TCheckbutton", background=BG_TRACK, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG_TRACK)])

        style.configure("Horizontal.TScale", background=BG_PANEL, troughcolor=BG)

        style.configure("TProgressbar", troughcolor=BG_PANEL,
                         background=ACCENT, bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

        style.configure("Vertical.TScrollbar", background=BG_PANEL,
                         troughcolor=BG, arrowcolor=ACCENT)

    def _build_divider(self, horizontal=True):
        if horizontal:
            line = tk.Frame(self.root, bg=DIVIDER, height=2)
            line.pack(side="top", fill="x")
        else:
            return tk.Frame(self.root, bg=DIVIDER, width=2)

    # ------------------------------------------------------------
    # Top bar: File menu + Add Track + Master Volume (dark grey)
    # ------------------------------------------------------------
    def _build_top_bar(self):
        top_bar = tk.Frame(self.root, bg=BG_PANEL, height=44)
        top_bar.pack(side="top", fill="x")
        top_bar.pack_propagate(False)
        self.top_bar = top_bar

        inner = tk.Frame(top_bar, bg=BG_PANEL)
        inner.pack(side="left", padx=10, pady=6)

        # --- custom dark File menu (native tk.Menu can be colored, unlike ttk) ---
        file_btn = tk.Menubutton(
            inner, text="File", bg=BG_PANEL, fg=ACCENT,
            activebackground=ACCENT_DIM, activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=4,
        )
        file_menu = tk.Menu(
            file_btn, tearoff=0, bg=BG_PANEL, fg=FG,
            activebackground=ACCENT_DIM, activeforeground="#ffffff",
        )
        file_menu.add_command(label="Save Project...", accelerator="Ctrl+S", command=self.save_project)
        file_menu.add_command(label="Load Project...", accelerator="Ctrl+O", command=self.load_project)
        file_menu.add_separator()
        file_menu.add_command(label="Export Mix...", accelerator="Ctrl+E", command=self.export_mix)
        file_menu.add_separator()
        file_menu.add_command(label="Keyboard Commands", command=self.show_keyboard_commands)
        file_menu.add_command(label="Settings", command=self.open_settings)
        file_menu.add_command(label="Load Auto-save JSON...", command=self._load_autosave_json)
        file_menu.add_command(label="Exit", command=self.root.quit)
        file_btn.config(menu=file_menu)
        file_btn.pack(side="left")

        ttk.Button(inner, text="+ Add Track", command=self.add_track).pack(side="left", padx=(16, 0))
        self.piano_btn = ttk.Button(inner, text="Piano Roll", command=self._toggle_piano_roll)
        self.piano_btn.pack(side="left", padx=(8, 0))
        self.drum_btn = ttk.Button(inner, text="Drum Machine", command=self._toggle_drum_machine)
        self.drum_btn.pack(side="left", padx=(8, 0))
        ttk.Button(inner, text="Split", command=self.split_selected_track).pack(side="left", padx=(8, 0))
        self.undo_btn = ttk.Button(inner, text="Undo", command=self.undo)
        self.undo_btn.pack(side="left", padx=(8, 0))
        self.redo_btn = ttk.Button(inner, text="Redo", command=self.redo)
        self.redo_btn.pack(side="left", padx=(4, 0))
        ttk.Button(inner, text="+ Marker", command=self.add_marker).pack(side="left", padx=(8, 0))
        self.autosave_btn = ttk.Button(inner, text="Auto-save: On", command=self.toggle_autosave)
        self.autosave_btn.pack(side="left", padx=(4, 0))
        ttk.Button(inner, text="Settings", command=self.open_settings).pack(side="left", padx=(8, 0))

        vol_frame = tk.Frame(top_bar, bg=BG_PANEL)
        vol_frame.pack(side="left", padx=(24, 0))
        tk.Label(vol_frame, text="Master Volume", bg=BG_PANEL, fg=FG).pack(side="left", padx=(0, 6))
        self.master_vol = tk.DoubleVar(value=100)
        ttk.Scale(
            vol_frame, from_=0, to=100, variable=self.master_vol,
            command=self._on_master_vol, orient="horizontal", length=150
        ).pack(side="left")

        mic_frame = tk.Frame(top_bar, bg=BG_PANEL)
        mic_frame.pack(side="left", padx=(16, 0))
        tk.Label(mic_frame, text="Mic", bg=BG_PANEL, fg=FG).pack(side="left", padx=(0, 4))
        self.input_device_var = tk.StringVar(value="Default Input")
        self.input_device_menu = ttk.Combobox(mic_frame, textvariable=self.input_device_var,
                                               state="readonly", width=18)
        self.input_device_menu.pack(side="left")
        self._populate_input_devices()
        tk.Label(mic_frame, text="Level", bg=BG_PANEL, fg=FG).pack(side="left", padx=(6, 3))
        self.input_meter = ttk.Progressbar(mic_frame, orient="horizontal", length=75,
                                           mode="determinate", maximum=1.0)
        self.input_meter.pack(side="left")

        bpm_frame = tk.Frame(top_bar, bg=BG_PANEL)
        bpm_frame.pack(side="left", padx=(16, 0))
        tk.Label(bpm_frame, text="BPM", bg=BG_PANEL, fg=FG).pack(side="left", padx=(0, 6))
        self.bpm_var = tk.IntVar(value=120)
        self.bpm_spin = tk.Spinbox(
            bpm_frame, from_=40, to=240, increment=1, width=5,
            textvariable=self.bpm_var, bg=BG_PANEL, fg=FG,
            insertbackground=FG, buttonbackground=BG_PANEL,
            relief="solid", bd=1, justify="center", command=self._on_bpm_changed
        )
        self.bpm_spin.pack(side="left")
        self.bpm_spin.bind("<Return>", lambda _e: self._on_bpm_changed())
        self.bpm_spin.bind("<FocusOut>", lambda _e: self._on_bpm_changed())

    def _on_bpm_changed(self):
        if not self._restoring_history:
            self._push_undo()
        try:
            bpm = int(self.bpm_var.get())
        except (TypeError, ValueError):
            bpm = 120
        self.bpm_var.set(max(40, min(240, bpm)))
        self._update_left_panel()

    def _update_loop_button(self):
        if hasattr(self, "loop_btn"):
            self.loop_btn.config(text="Loop: On" if self.loop_enabled else "Loop: Off")

    def _normalize_loop(self):
        total = self.engine.total_frames()
        if total <= 0:
            self.loop_start = 0
            self.loop_end = 0
            self.loop_enabled = False
            self._update_loop_button()
            return
        self.loop_start = max(0, min(int(self.loop_start), total - 1))
        self.loop_end = max(self.loop_start + 1, min(int(self.loop_end or total), total))
        if self.loop_end <= self.loop_start:
            self.loop_start = 0
            self.loop_end = total

    def toggle_loop(self):
        if self.engine.total_frames() <= 0:
            messagebox.showinfo(APP_NAME, "Add a track before enabling loop mode.")
            return
        if self.loop_end <= self.loop_start:
            self.loop_start = 0
            self.loop_end = self.engine.total_frames()
        self.loop_enabled = not self.loop_enabled
        if self.loop_enabled and not (self.loop_start <= self.engine.position < self.loop_end):
            self.engine.seek(self.loop_start)
        self._update_loop_button()
        self._update_left_panel()

    def set_loop_start(self):
        total = self.engine.total_frames()
        if total <= 0:
            return
        self.loop_start = max(0, min(self.engine.position, total - 1))
        if self.loop_end <= self.loop_start:
            self.loop_end = total
        self._update_left_panel()

    def set_loop_end(self):
        total = self.engine.total_frames()
        if total <= 0:
            return
        self.loop_end = max(1, min(self.engine.position, total))
        if self.loop_end <= self.loop_start:
            self.loop_start = 0
        self._update_left_panel()

    # ------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------
    def _capture_state(self):
        tracks = []
        for t in self.engine.tracks:
            tracks.append({
                "obj": t,
                "name": t.name,
                "color": t.color,
                "volume": t.volume,
                "muted": t.muted,
                "solo": t.solo,
                "pan": getattr(t, "pan", 0.0),
                "start_frame": t.start_frame,
                "trim_start": t.trim_start,
                "trim_end": t.trim_end,
                "fade_in": t.fade_in,
                "fade_out": t.fade_out,
                "effects": dict(t.effects),
            })
        return {
            "tracks": tracks,
            "selected": self.selected_track,
            "piano_notes": set(self.piano_notes),
            "piano_instrument": self.piano_instrument.get(),
            "drum_pattern": {k: set(v) for k, v in self.drum_pattern.items()},
            "loop_enabled": self.loop_enabled,
            "loop_start": self.loop_start,
            "loop_end": self.loop_end,
            "bpm": int(self.bpm_var.get()),
            "markers": [dict(m) for m in self.markers],
            "loop_enabled": self.loop_enabled,
            "loop_start": self.loop_start,
            "loop_end": self.loop_end,
            "position": int(self.engine.position),
        }

    def _state_signature(self, state):
        tracks = []
        for snap in state["tracks"]:
            tracks.append((
                snap["obj"], snap["name"], snap["color"], round(snap["volume"], 6),
                snap["muted"], snap["solo"], round(snap.get("pan", 0.0), 6), snap["start_frame"], snap["trim_start"],
                snap["trim_end"], round(snap.get("fade_in", 0.0), 6),
                round(snap.get("fade_out", 0.0), 6), tuple(sorted(snap["effects"].items())),
            ))
        drums = tuple(sorted((k, tuple(sorted(v))) for k, v in state["drum_pattern"].items()))
        return (tuple(tracks), tuple(sorted(state["piano_notes"])), state["piano_instrument"],
                drums, state["loop_enabled"], state["loop_start"], state["loop_end"],
                state["bpm"], tuple((m["frame"], m["name"]) for m in state.get("markers", [])))

    def _push_undo(self):
        if self._restoring_history:
            return
        state = self._capture_state()
        signature = self._state_signature(state)
        if signature == self._last_history_signature:
            return
        self._undo_stack.append(state)
        if len(self._undo_stack) > MAX_UNDO_HISTORY:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._last_history_signature = signature
        self._update_history_buttons()

    def _restore_state(self, state):
        self._restoring_history = True
        try:
            self.engine.stop()
            restored_tracks = []
            for snap in state["tracks"]:
                t = snap["obj"]
                t.name = snap["name"]
                t.color = snap["color"]
                t.volume = snap["volume"]
                t.muted = snap["muted"]
                t.solo = snap["solo"]
                t.pan = float(snap.get("pan", 0.0))
                t.start_frame = snap["start_frame"]
                t.trim_start = snap["trim_start"]
                t.trim_end = snap["trim_end"]
                t.fade_in = float(snap.get("fade_in", 0.0))
                t.fade_out = float(snap.get("fade_out", 0.0))
                t.effects = dict(snap["effects"])
                t.invalidate_effect_cache()
                restored_tracks.append(t)
            with self.engine._lock:
                self.engine.tracks = restored_tracks
                self.engine.position = max(0, min(int(state.get("position", 0)), self.engine.total_frames()))
            self.selected_track = state["selected"] if state["selected"] in restored_tracks else (restored_tracks[-1] if restored_tracks else None)
            self.piano_notes = set(state["piano_notes"])
            self.piano_instrument.set(state["piano_instrument"] if state["piano_instrument"] in ("Piano", "Guitar") else "Piano")
            self.drum_pattern = {k: set(v) for k, v in state.get("drum_pattern", {r: set() for r in DRUM_ROWS}).items()}
            self.bpm_var.set(max(40, min(240, int(state["bpm"]))))
            self.markers = [dict(m) for m in state.get("markers", [])]
            self.loop_enabled = bool(state["loop_enabled"])
            self.loop_start = int(state["loop_start"])
            self.loop_end = int(state["loop_end"])
            self._rebuild_track_rows()
            self._draw_piano_roll()
            self._refresh_drum_buttons()
            self._update_loop_button()
            self._draw_ruler()
            self._update_left_panel()
        finally:
            self._restoring_history = False
            self._update_history_buttons()

    def _update_history_buttons(self):
        if hasattr(self, "undo_btn"):
            self.undo_btn.config(state="normal" if self._undo_stack else "disabled")
        if hasattr(self, "redo_btn"):
            self.redo_btn.config(state="normal" if self._redo_stack else "disabled")

    def undo(self):
        if not self._undo_stack:
            return
        current = self._capture_state()
        state = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._restore_state(state)
        self._last_history_signature = self._state_signature(self._capture_state())

    def redo(self):
        if not self._redo_stack:
            return
        current = self._capture_state()
        state = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._restore_state(state)
        self._last_history_signature = self._state_signature(self._capture_state())

    # ------------------------------------------------------------
    # Main area: left placeholder panel | divider | ruler + tracks
    # ------------------------------------------------------------
    def _build_main_area(self):
        # Main view container. The normal timeline and piano roll can be
        # switched with the button in the top bar.
        self.main_area = tk.Frame(self.root, bg=BG)
        self.main_area.pack(side="top", fill="both", expand=True)

        self.timeline_view = tk.Frame(self.main_area, bg=BG)
        self.timeline_view.pack(fill="both", expand=True)

        # --- left panel ---
        left_panel = tk.Frame(self.timeline_view, bg=BG_PANEL, width=LEFT_PANEL_WIDTH)
        left_panel.pack(side="left", fill="y")
        left_panel.pack_propagate(False)

        tk.Label(left_panel, text="Project", bg=BG_PANEL, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(pady=(10, 6))

        self.left_tracks_label = tk.Label(
            left_panel, text="Tracks: 0", bg=BG_PANEL, fg=FG_DIM, anchor="w"
        )
        self.left_tracks_label.pack(fill="x", padx=12)

        self.left_length_label = tk.Label(
            left_panel, text="Length: 00:00", bg=BG_PANEL, fg=FG_DIM, anchor="w"
        )
        self.left_length_label.pack(fill="x", padx=12, pady=(2, 0))

        self.left_bpm_label = tk.Label(
            left_panel, text="BPM: 120", bg=BG_PANEL, fg=FG_DIM, anchor="w"
        )
        self.left_bpm_label.pack(fill="x", padx=12, pady=(2, 10))

        tk.Frame(left_panel, bg=GRID_LINE, height=1).pack(fill="x", padx=10, pady=2)

        tk.Label(left_panel, text="Selected Track", bg=BG_PANEL, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(pady=(10, 6))

        self.left_selected_label = tk.Label(
            left_panel, text="None", bg=BG_PANEL, fg=FG,
            anchor="w", wraplength=145, justify="left"
        )
        self.left_selected_label.pack(fill="x", padx=12)

        self.left_position_label = tk.Label(
            left_panel, text="Position: 00:00", bg=BG_PANEL, fg=FG_DIM, anchor="w"
        )
        self.left_position_label.pack(fill="x", padx=12, pady=(3, 0))

        self.left_duration_label = tk.Label(
            left_panel, text="Length: 00:00", bg=BG_PANEL, fg=FG_DIM, anchor="w"
        )
        self.left_duration_label.pack(fill="x", padx=12, pady=(2, 8))

        tk.Frame(left_panel, bg=GRID_LINE, height=1).pack(fill="x", padx=10, pady=2)

        tk.Label(left_panel, text="Quick Actions", bg=BG_PANEL, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(pady=(10, 6))
        ttk.Button(left_panel, text="Split at Playhead",
                   command=self.split_selected_track).pack(fill="x", padx=10, pady=2)
        ttk.Button(left_panel, text="Rename Track",
                   command=self.rename_selected_track).pack(fill="x", padx=10, pady=2)
        ttk.Button(left_panel, text="Change Color",
                   command=self.cycle_selected_track_color).pack(fill="x", padx=10, pady=2)
        ttk.Button(left_panel, text="Open Effects Rack",
                   command=lambda: self.open_effects_rack(self.selected_track)).pack(fill="x", padx=10, pady=2)

        # --- vertical divider ---
        tk.Frame(self.timeline_view, bg=DIVIDER, width=2).pack(side="left", fill="y")

        # --- right side: ruler + scrollable track list ---
        right_area = tk.Frame(self.timeline_view, bg=BG)
        right_area.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self.ruler_canvas = tk.Canvas(
            right_area, width=TIMELINE_WIDTH, height=RULER_HEIGHT,
            bg=BG, highlightthickness=0
        )
        self.ruler_canvas.pack(side="top", anchor="w")

        track_container = tk.Frame(right_area, bg=BG)
        track_container.pack(side="top", fill="both", expand=True, pady=(4, 0))

        canvas = tk.Canvas(track_container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(track_container, orient="vertical", command=canvas.yview)
        self.track_frame = tk.Frame(canvas, bg=BG)

        self.track_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.track_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.empty_label = tk.Label(
            self.track_frame,
            text="No tracks yet — click '+ Add Track' to load a .wav file.",
            bg=BG, fg=FG_DIM,
        )
        self.empty_label.pack(pady=20, anchor="w")

        self._build_piano_roll()
        self._build_drum_machine()

    def _build_piano_roll(self):
        self.piano_view = tk.Frame(self.main_area, bg=BG)

        header = tk.Frame(self.piano_view, bg=BG_PANEL, height=38)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="Piano Roll", bg=BG_PANEL, fg=FG,
            font=("Segoe UI", 10, "bold")
        ).pack(side="left", padx=(12, 8), pady=9)

        tk.Label(
            header, text="Instrument:", bg=BG_PANEL, fg=FG
        ).pack(side="left", padx=(0, 4), pady=8)

        # Native Tk OptionMenu is used deliberately so the instrument selector
        # is always visible on Windows with the dark ttk theme.
        self.instrument_menu = tk.OptionMenu(
            header, self.piano_instrument, "Piano", "Guitar"
        )
        self.instrument_menu.configure(
            bg=BG_PANEL, fg=ACCENT, activebackground=ACCENT_DIM,
            activeforeground="#ffffff", highlightthickness=1,
            highlightbackground=ACCENT_DIM, highlightcolor=ACCENT,
            relief="flat", bd=0, width=9
        )
        self.instrument_menu["menu"].configure(
            bg=BG_PANEL, fg=FG, activebackground=ACCENT_DIM,
            activeforeground="#ffffff"
        )
        self.instrument_menu.pack(side="left", padx=(0, 12), pady=5)

        tk.Label(
            header, text="Click a cell to add/remove a MIDI note",
            bg=BG_PANEL, fg=FG_DIM
        ).pack(side="left", padx=4)

        ttk.Button(
            header, text="+ Add to Timeline", command=self.add_piano_roll_to_timeline
        ).pack(side="right", padx=10, pady=6)

        body = tk.Frame(self.piano_view, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        self.piano_keys_canvas = tk.Canvas(
            body, width=PIANO_KEY_WIDTH, bg=BG_PANEL,
            highlightthickness=0, yscrollincrement=PIANO_KEY_HEIGHT
        )
        self.piano_keys_canvas.pack(side="left", fill="y")

        self.piano_canvas = tk.Canvas(
            body, bg=BG, highlightthickness=0
        )
        self.piano_canvas.pack(side="left", fill="both", expand=True)

        self.piano_y_scroll = ttk.Scrollbar(
            body, orient="vertical", command=self._piano_yview
        )
        self.piano_y_scroll.pack(side="right", fill="y")

        self.piano_canvas.configure(
            yscrollcommand=self.piano_y_scroll.set
        )

        self.piano_canvas.bind("<Button-1>", self._piano_click)
        self.piano_canvas.bind("<Configure>", lambda e: self._draw_piano_roll())

        self._draw_piano_roll()

    def _build_drum_machine(self):
        self.drum_view = tk.Frame(self.main_area, bg=BG)

        header = tk.Frame(self.drum_view, bg=BG_PANEL, height=42)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Drum Beat Maker", bg=BG_PANEL, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=12, pady=10)
        tk.Label(header, text="16-step sequencer", bg=BG_PANEL, fg=FG_DIM).pack(side="left", padx=4)
        ttk.Button(header, text="Clear", command=self.clear_drum_pattern).pack(side="right", padx=5, pady=7)
        ttk.Button(header, text="+ Add to Timeline", command=self.add_drum_to_timeline).pack(side="right", padx=5, pady=7)
        ttk.Button(header, text="Timeline", command=self._show_timeline).pack(side="right", padx=5, pady=7)

        body = tk.Frame(self.drum_view, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        self.drum_step_buttons = {}
        label_w = 90
        for step in range(DRUM_STEPS):
            tk.Label(body, text=str(step + 1), bg=BG, fg=FG_DIM,
                     width=4).grid(row=0, column=step + 1, padx=2, pady=(0, 6))
        for r, drum in enumerate(DRUM_ROWS, start=1):
            tk.Label(body, text=drum, bg=BG, fg=FG, width=label_w // 10,
                     anchor="w").grid(row=r, column=0, padx=(0, 8), pady=3, sticky="w")
            for step in range(DRUM_STEPS):
                btn = tk.Button(body, width=3, height=1, text="",
                                bg=BG_PANEL, fg=FG, activebackground=ACCENT_DIM,
                                relief="flat", bd=0, highlightthickness=1,
                                highlightbackground=GRID_LINE,
                                command=lambda d=drum, st=step: self._toggle_drum_step(d, st))
                btn.grid(row=r, column=step + 1, padx=2, pady=3)
                self.drum_step_buttons[(drum, step)] = btn
        self._refresh_drum_buttons()

    def _toggle_drum_step(self, drum, step):
        self._push_undo()
        slots = self.drum_pattern.setdefault(drum, set())
        if step in slots:
            slots.remove(step)
        else:
            slots.add(step)
        self._refresh_drum_buttons()

    def _refresh_drum_buttons(self):
        for (drum, step), btn in getattr(self, "drum_step_buttons", {}).items():
            active = step in self.drum_pattern.get(drum, set())
            accent = ACCENT if active else BG_PANEL
            btn.configure(bg=accent)
            btn.configure(text="●" if active else "")

    def clear_drum_pattern(self):
        self._push_undo()
        self.drum_pattern = {row: set() for row in DRUM_ROWS}
        self._refresh_drum_buttons()

    def _toggle_drum_machine(self):
        if self.drum_machine_visible:
            self._show_timeline()
        else:
            self._show_drum_machine()

    def _show_drum_machine(self):
        if getattr(self, "piano_roll_visible", False):
            self.piano_view.pack_forget()
            self.piano_roll_visible = False
        self.timeline_view.pack_forget()
        self.drum_view.pack(fill="both", expand=True)
        self.drum_machine_visible = True
        self.drum_btn.config(text="Timeline")
        if hasattr(self, "piano_btn"):
            self.piano_btn.config(text="Piano Roll")

    def _render_drum_pattern(self):
        bpm = max(40, min(240, int(self.bpm_var.get())))
        step_seconds = 60.0 / bpm / 4.0
        total_steps = max(16, max((max(v) + 1 for v in self.drum_pattern.values() if v), default=16))
        total_seconds = total_steps * step_seconds + 0.25
        sr = self.engine.sample_rate
        total_frames = int(np.ceil(total_seconds * sr))
        audio = np.zeros((total_frames, 2), dtype=np.float32)

        def add_sound(start_frame, wave):
            end = min(total_frames, start_frame + len(wave))
            if end > start_frame:
                audio[start_frame:end, 0] += wave[:end-start_frame]
                audio[start_frame:end, 1] += wave[:end-start_frame]

        rng = np.random.default_rng(12345)
        for step in range(total_steps):
            start = int(round(step * step_seconds * sr))
            if step in self.drum_pattern["Kick"]:
                n = int(0.35 * sr)
                t = np.arange(n, dtype=np.float32) / sr
                freq = 120.0 * np.exp(-t * 18.0) + 42.0
                phase = 2 * np.pi * np.cumsum(freq) / sr
                wave = np.sin(phase) * np.exp(-t * 10.0) * 0.65
                add_sound(start, wave.astype(np.float32))
            if step in self.drum_pattern["Snare"] or step in self.drum_pattern["Clap"]:
                n = int(0.20 * sr)
                noise = rng.normal(0, 1, n).astype(np.float32)
                t = np.arange(n, dtype=np.float32) / sr
                env = np.exp(-t * 25.0)
                if step in self.drum_pattern["Snare"]:
                    tone = np.sin(2 * np.pi * 190.0 * t) * np.exp(-t * 22.0)
                    add_sound(start, (noise * env * 0.28 + tone * 0.16).astype(np.float32))
                if step in self.drum_pattern["Clap"]:
                    add_sound(start, (noise * env * 0.20).astype(np.float32))
            if step in self.drum_pattern["Closed Hat"]:
                n = int(0.07 * sr)
                noise = rng.normal(0, 1, n).astype(np.float32)
                t = np.arange(n, dtype=np.float32) / sr
                add_sound(start, (noise * np.exp(-t * 70.0) * 0.13).astype(np.float32))
            if step in self.drum_pattern["Open Hat"]:
                n = int(0.32 * sr)
                noise = rng.normal(0, 1, n).astype(np.float32)
                t = np.arange(n, dtype=np.float32) / sr
                add_sound(start, (noise * np.exp(-t * 12.0) * 0.10).astype(np.float32))
        np.clip(audio, -1.0, 1.0, out=audio)
        return audio

    def add_drum_to_timeline(self):
        if not any(self.drum_pattern.values()):
            messagebox.showinfo(APP_NAME, "Add at least one drum hit first.")
            return
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_dir = os.getcwd()
        recordings_dir = os.path.join(script_dir, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        path = os.path.join(recordings_dir, f"drum_beat_{time.strftime('%Y%m%d_%H%M%S')}.wav")
        try:
            sf.write(path, self._render_drum_pattern(), self.engine.sample_rate)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't render drum beat:\n{e}")
            return
        track = self._add_new_track(
            path,
            initial_name="Drum Beat",
            initial_color=TRACK_COLORS[len(self.engine.tracks) % len(TRACK_COLORS)],
            initial_start_frame=self.engine.position,
        )
        if track is not None:
            self.select_track(track)
            self._show_timeline()

    def _piano_yview(self, *args):
        self.piano_canvas.yview(*args)
        self.piano_keys_canvas.yview(*args)

    @staticmethod
    def _midi_name(midi):
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return f"{names[midi % 12]}{midi // 12 - 1}"

    def _draw_piano_roll(self):
        if not hasattr(self, "piano_canvas"):
            return

        total_rows = PIANO_OCTAVES * 12
        total_height = total_rows * PIANO_KEY_HEIGHT
        total_width = PIANO_BEATS * PIANO_NOTE_WIDTH

        self.piano_canvas.delete("all")
        self.piano_keys_canvas.delete("all")

        self.piano_canvas.configure(
            scrollregion=(0, 0, total_width, total_height)
        )
        self.piano_keys_canvas.configure(
            scrollregion=(0, 0, PIANO_KEY_WIDTH, total_height)
        )

        black_keys = {1, 3, 6, 8, 10}

        # Piano keys + grid
        for row in range(total_rows):
            midi = PIANO_LOW_MIDI + total_rows - 1 - row
            y = row * PIANO_KEY_HEIGHT
            pitch_class = midi % 12
            is_black = pitch_class in black_keys

            key_fill = "#303030" if is_black else "#e2e2e2"
            key_text = "#ffffff" if is_black else "#111111"

            self.piano_keys_canvas.create_rectangle(
                0, y, PIANO_KEY_WIDTH, y + PIANO_KEY_HEIGHT,
                fill=key_fill, outline="#555555"
            )
            self.piano_keys_canvas.create_text(
                PIANO_KEY_WIDTH - 5, y + PIANO_KEY_HEIGHT / 2,
                text=self._midi_name(midi), anchor="e", fill=key_text,
                font=("Segoe UI", 8)
            )

            row_fill = "#292929" if is_black else "#232323"
            self.piano_canvas.create_rectangle(
                0, y, total_width, y + PIANO_KEY_HEIGHT,
                fill=row_fill, outline="#343434"
            )

        # Beat grid
        for beat in range(PIANO_BEATS + 1):
            x = beat * PIANO_NOTE_WIDTH
            fill = ACCENT_DIM if beat % 4 == 0 else GRID_LINE
            self.piano_canvas.create_line(
                x, 0, x, total_height, fill=fill
            )

        # Beat labels across the top inside the roll
        for beat in range(PIANO_BEATS):
            if beat % 4 == 0:
                self.piano_canvas.create_text(
                    beat * PIANO_NOTE_WIDTH + 4, 4,
                    text=str(beat // 4 + 1),
                    anchor="nw", fill=FG_DIM,
                    font=("Segoe UI", 8)
                )

        # Notes
        for midi, beat in self.piano_notes:
            row = PIANO_LOW_MIDI + total_rows - 1 - midi
            if row < 0 or row >= total_rows:
                continue
            x1 = beat * PIANO_NOTE_WIDTH + 2
            y1 = row * PIANO_KEY_HEIGHT + 2
            x2 = (beat + 1) * PIANO_NOTE_WIDTH - 2
            y2 = (row + 1) * PIANO_KEY_HEIGHT - 2
            self.piano_canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=ACCENT, outline="#ffffff"
            )
            self.piano_canvas.create_text(
                x1 + 5, (y1 + y2) / 2,
                text=self._midi_name(midi),
                anchor="w", fill="#101010",
                font=("Segoe UI", 7, "bold")
            )

    def _piano_click(self, event):
        self._push_undo()
        x = self.piano_canvas.canvasx(event.x)
        y = self.piano_canvas.canvasy(event.y)

        beat = int(x // PIANO_NOTE_WIDTH)
        total_rows = PIANO_OCTAVES * 12
        row = int(y // PIANO_KEY_HEIGHT)
        midi = PIANO_LOW_MIDI + total_rows - 1 - row

        if 0 <= beat < PIANO_BEATS and PIANO_LOW_MIDI <= midi < PIANO_LOW_MIDI + total_rows:
            key = (midi, beat)
            if key in self.piano_notes:
                self.piano_notes.remove(key)
            else:
                self.piano_notes.add(key)
            self._draw_piano_roll()

    def add_piano_roll_to_timeline(self):
        """Render the current piano-roll notes to WAV and add the result as a normal audio track."""
        if not self.piano_notes:
            messagebox.showinfo(APP_NAME, "Add at least one note in the Piano Roll first.")
            return

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_dir = os.getcwd()

        recordings_dir = os.path.join(script_dir, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        filename = f"piano_roll_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        path = os.path.join(recordings_dir, filename)

        # One beat is a quarter note at 120 BPM. Each Piano Roll cell is one beat.
        seconds_per_beat = 60.0 / float(self.bpm_var.get())
        note_seconds = seconds_per_beat
        total_seconds = max(
            1.0, (max(beat for _midi, beat in self.piano_notes) + 1) * seconds_per_beat
        )
        total_frames = int(np.ceil(total_seconds * self.engine.sample_rate))
        audio = np.zeros((total_frames, 2), dtype=np.float32)

        for midi, beat in sorted(self.piano_notes):
            freq = 440.0 * (2.0 ** ((midi - 69) / 12.0))
            start = int(round(beat * seconds_per_beat * self.engine.sample_rate))
            length = int(round(note_seconds * self.engine.sample_rate))
            end = min(total_frames, start + length)
            if start >= end:
                continue

            n = end - start
            t = np.arange(n, dtype=np.float32) / self.engine.sample_rate

            if self.piano_instrument.get() == "Guitar":
                # Plucked-string style sound using a short noisy excitation
                # followed by a decaying harmonic waveform.
                rng = np.random.default_rng(midi * 1000 + beat)
                body = (
                    0.72 * np.sin(2 * np.pi * freq * t)
                    + 0.18 * np.sin(2 * np.pi * freq * 2 * t)
                    + 0.07 * np.sin(2 * np.pi * freq * 3 * t)
                )
                pluck = rng.normal(0.0, 1.0, n).astype(np.float32)
                attack = min(n, max(1, int(0.004 * self.engine.sample_rate)))
                pluck[attack:] *= np.exp(-np.arange(n - attack, dtype=np.float32) /
                                         max(1.0, self.engine.sample_rate * 0.08))
                wave = (0.72 * body + 0.28 * pluck)
                envelope = np.exp(-np.arange(n, dtype=np.float32) /
                                  max(1.0, self.engine.sample_rate * 0.55))
                wave *= envelope * 0.16
            else:
                # Piano-style sound: fundamental plus soft upper harmonics
                # with a quick attack and natural decay.
                wave = (
                    0.70 * np.sin(2 * np.pi * freq * t)
                    + 0.20 * np.sin(2 * np.pi * freq * 2 * t)
                    + 0.10 * np.sin(2 * np.pi * freq * 3 * t)
                )
                envelope = np.ones(n, dtype=np.float32)
                attack = min(n, max(1, int(0.01 * self.engine.sample_rate)))
                release = min(n, max(1, int(0.12 * self.engine.sample_rate)))
                envelope[:attack] = np.linspace(0.0, 1.0, attack, dtype=np.float32)
                envelope[-release:] *= np.linspace(1.0, 0.0, release, dtype=np.float32)
                wave *= envelope * 0.18

            audio[start:end, 0] += wave
            audio[start:end, 1] += wave

        np.clip(audio, -1.0, 1.0, out=audio)

        try:
            sf.write(path, audio, self.engine.sample_rate)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't render Piano Roll:\n{e}")
            return

        instrument_name = self.piano_instrument.get()
        track = self._add_new_track(
            path,
            initial_name=f"Piano Roll - {instrument_name}",
            initial_color=TRACK_COLORS[len(self.engine.tracks) % len(TRACK_COLORS)]
        )
        if track is not None:
            self.select_track(track)
            self._show_timeline()

    def _show_timeline(self):
        if getattr(self, "drum_machine_visible", False):
            self.drum_view.pack_forget()
            self.drum_machine_visible = False
            if hasattr(self, "drum_btn"):
                self.drum_btn.config(text="Drum Machine")
        if self.piano_roll_visible:
            self.piano_view.pack_forget()
            self.timeline_view.pack(fill="both", expand=True)
            self.piano_roll_visible = False
            self.piano_btn.config(text="Piano Roll")

    def _show_piano_roll(self):
        if getattr(self, "drum_machine_visible", False):
            self.drum_view.pack_forget()
            self.drum_machine_visible = False
            if hasattr(self, "drum_btn"):
                self.drum_btn.config(text="Drum Machine")
        if not self.piano_roll_visible:
            self.timeline_view.pack_forget()
            self.piano_view.pack(fill="both", expand=True)
            self.piano_roll_visible = True
            self.piano_btn.config(text="Timeline")
            self._draw_piano_roll()

    def _bind_shortcuts(self):
        self.root.bind_all("<space>", self._shortcut_play_pause)
        self.root.bind_all("<KeyPress-s>", self._shortcut_stop)
        self.root.bind_all("<KeyPress-r>", self._shortcut_record)
        self.root.bind_all("<Home>", self._shortcut_home)
        self.root.bind_all("<End>", self._shortcut_end)
        self.root.bind_all("<KeyPress-p>", self._shortcut_piano)
        self.root.bind_all("<KeyPress-b>", self._toggle_drum_view_from_shortcut)
        self.root.bind_all("<KeyPress-t>", self._shortcut_timeline)
        self.root.bind_all("<F2>", self._shortcut_rename)
        self.root.bind_all("<KeyPress-c>", self._shortcut_color)
        self.root.bind_all("<KeyPress-f>", self._shortcut_effects)
        self.root.bind_all("<KeyPress-d>", self._shortcut_split)
        self.root.bind_all("<Delete>", self._shortcut_delete_track)
        self.root.bind_all("<Control-s>", self._shortcut_save)
        self.root.bind_all("<Control-o>", self._shortcut_load)
        self.root.bind_all("<Control-e>", self._shortcut_export)
        self.root.bind_all("<Control-t>", self._shortcut_timeline)
        self.root.bind_all("<Control-z>", self._shortcut_undo)
        self.root.bind_all("<Control-y>", self._shortcut_redo)
        self.root.bind_all("<KeyPress-l>", self._shortcut_loop)

    @staticmethod
    def _typing_widget(widget):
        return isinstance(widget, (tk.Entry, ttk.Entry, tk.Text))

    def _shortcut_play_pause(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self._toggle_play_pause(); return "break"

    def _shortcut_stop(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.stop(); return "break"

    def _shortcut_record(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.toggle_recording(); return "break"

    def _shortcut_home(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.engine.seek(0); return "break"

    def _shortcut_end(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.engine.seek(self.engine.total_frames()); return "break"

    def _shortcut_piano(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self._show_piano_roll(); return "break"

    def _shortcut_timeline(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self._show_timeline(); return "break"

    def _shortcut_rename(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.rename_selected_track(); return "break"

    def _shortcut_color(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.cycle_selected_track_color(); return "break"

    def _shortcut_split(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.split_selected_track(); return "break"

    def _shortcut_effects(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.open_effects_rack(self.selected_track); return "break"

    def _shortcut_delete_track(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.remove_selected_track(); return "break"

    def _shortcut_save(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.save_project(); return "break"

    def _shortcut_load(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.load_project(); return "break"

    def _shortcut_export(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.export_mix(); return "break"

    def _shortcut_undo(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.undo(); return "break"

    def _shortcut_redo(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.redo(); return "break"

    def _shortcut_loop(self, _event=None):
        if self._typing_widget(self.root.focus_get()): return
        self.toggle_loop(); return "break"

    def open_effects_rack(self, track):
        if track is None or track not in self.engine.tracks:
            messagebox.showinfo(APP_NAME, "Select a track first.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Effects — {track.name}")
        win.geometry("430x500")
        win.minsize(400, 450)
        win.configure(bg=BG)
        win.transient(self.root)

        tk.Label(win, text=f"Effects Rack: {track.name}", bg=BG_PANEL, fg=FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=0, pady=0, ipady=9)

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        vars_ = {}

        def add_slider(label, key, lo, hi, resolution=0.01, formatter=None):
            frame = tk.Frame(body, bg=BG)
            frame.pack(fill="x", pady=7)
            value_label = tk.Label(frame, text="", bg=BG, fg=FG_DIM, width=9, anchor="e")
            value_label.pack(side="right")
            tk.Label(frame, text=label, bg=BG, fg=FG, width=13, anchor="w").pack(side="left")
            var = tk.DoubleVar(value=track.effects[key])
            vars_[key] = var

            def changed(_=None, k=key, v=var, vl=value_label):
                track.effects[k] = float(v.get())
                track.invalidate_effect_cache()
                current = float(v.get())
                vl.config(text=(formatter(current) if formatter else f"{current:.2f}"))

            scale = tk.Scale(frame, from_=lo, to=hi, resolution=resolution,
                             orient="horizontal", variable=var, command=changed,
                             bg=BG, fg=FG, troughcolor=BG_PANEL, highlightthickness=0,
                             activebackground=ACCENT, length=230)
            scale.pack(side="left", padx=5, fill="x", expand=True)
            changed()

        add_slider("Gain", "gain", -24, 12, 0.1, lambda v: f"{v:+.1f} dB")
        add_slider("Delay", "delay", 0, 1, 0.01, lambda v: f"{v*100:.0f}%")
        add_slider("Delay Time", "delay_time", 0.03, 1.0, 0.01, lambda v: f"{v:.2f}s")
        add_slider("Reverb", "reverb", 0, 1, 0.01, lambda v: f"{v*100:.0f}%")
        add_slider("Distortion", "distortion", 0, 1, 0.01, lambda v: f"{v*100:.0f}%")
        add_slider("Compressor", "compressor", 0, 1, 0.01, lambda v: f"{v*100:.0f}%")
        add_slider("High-pass", "highpass", 20, 10000, 10, lambda v: f"{v:.0f} Hz")
        add_slider("Low-pass", "lowpass", 1000, 20000, 10, lambda v: f"{v:.0f} Hz")

        buttons = tk.Frame(win, bg=BG_PANEL)
        buttons.pack(fill="x", side="bottom", padx=0, pady=0, ipady=7)

        def reset():
            track.effects.update({
                "gain": 0.0, "delay": 0.0, "delay_time": 0.25,
                "reverb": 0.0, "distortion": 0.0, "compressor": 0.0,
                "lowpass": 20000.0, "highpass": 20.0,
            })
            track.invalidate_effect_cache()
            for key, var in vars_.items():
                var.set(track.effects[key])

        def vocal_preset():
            track.effects.update({
                "gain": 2.0, "delay": 0.0, "delay_time": 0.18,
                "reverb": 0.10, "distortion": 0.0, "compressor": 0.55,
                "lowpass": 16000.0, "highpass": 80.0,
            })
            track.invalidate_effect_cache()
            for key, var in vars_.items():
                var.set(track.effects[key])

        ttk.Button(buttons, text="Vocal Preset", command=vocal_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="Reset Effects", command=reset).pack(side="left", padx=12)
        ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right", padx=12)

        tk.Label(body, text="Effects are applied to playback and export.",
                 bg=BG, fg=FG_DIM).pack(anchor="w", pady=(6, 0))

    def _populate_midi_inputs(self):
        names = []
        if mido is not None:
            try:
                names = list(mido.get_input_names())
            except Exception:
                names = []
        self.midi_input_names = ["No MIDI Input"] + names
        if hasattr(self, "midi_input_menu"):
            self.midi_input_menu["values"] = self.midi_input_names
            try:
                current = self.midi_input_names.index(self.midi_input_name)
            except ValueError:
                current = 0
            self.midi_input_menu.current(current)

    def _set_midi_input(self, _event=None):
        if hasattr(self, "midi_input_menu"):
            self.midi_input_name = self.midi_input_menu.get() or "No MIDI Input"
        return "break"

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("OpenDAW Settings")
        win.geometry("620x560")
        win.minsize(560, 500)
        win.configure(bg=BG)
        win.transient(self.root)

        tk.Label(win, text="Settings", bg=BG_PANEL, fg=FG,
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x", ipady=10, padx=0)

        device_frame = tk.LabelFrame(win, text="Audio / MIDI Inputs", bg=BG, fg=FG,
                                     font=("Segoe UI", 9, "bold"),
                                     highlightbackground=ACCENT_DIM, highlightthickness=1)
        device_frame.pack(fill="x", padx=14, pady=14)

        mic_row = tk.Frame(device_frame, bg=BG)
        mic_row.pack(fill="x", padx=12, pady=(12, 7))
        tk.Label(mic_row, text="Microphone / Audio Input", bg=BG, fg=FG, width=24, anchor="w").pack(side="left")
        mic_menu = ttk.Combobox(mic_row, textvariable=self.input_device_var,
                                state="readonly", width=38)
        mic_menu.pack(side="left", fill="x", expand=True)
        mic_menu["values"] = getattr(self, "input_device_names", ["Default Input"])
        try:
            idx = self.input_device_names.index(self.input_device_var.get())
        except (ValueError, AttributeError):
            idx = 0
        mic_menu.current(idx if 0 <= idx < len(mic_menu["values"]) else 0)

        midi_row = tk.Frame(device_frame, bg=BG)
        midi_row.pack(fill="x", padx=12, pady=7)
        tk.Label(midi_row, text="MIDI Input", bg=BG, fg=FG, width=24, anchor="w").pack(side="left")
        self.midi_input_menu = ttk.Combobox(midi_row, textvariable=tk.StringVar(value=self.midi_input_name),
                                            state="readonly", width=38)
        self.midi_input_menu.pack(side="left", fill="x", expand=True)
        self._populate_midi_inputs()
        if mido is None:
            tk.Label(device_frame, text="MIDI device listing requires: pip install mido python-rtmidi",
                     bg=BG, fg=FG_DIM).pack(anchor="w", padx=12, pady=(0, 10))

        def refresh():
            self._populate_input_devices()
            mic_menu["values"] = self.input_device_names
            try:
                mic_menu.current(self.input_device_names.index(self.input_device_var.get()))
            except ValueError:
                mic_menu.current(0)
            self._populate_midi_inputs()

        ttk.Button(device_frame, text="Refresh Devices", command=refresh).pack(anchor="e", padx=12, pady=(4, 12))
        mic_menu.bind("<<ComboboxSelected>>", lambda _e: self.input_device_var.set(mic_menu.get()))
        self.midi_input_menu.bind("<<ComboboxSelected>>", self._set_midi_input)

        keys_frame = tk.LabelFrame(win, text="Keyboard Commands", bg=BG, fg=FG,
                                   font=("Segoe UI", 9, "bold"),
                                   highlightbackground=ACCENT_DIM, highlightthickness=1)
        keys_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        keys = [
            ("Space", "Play / Pause"), ("S", "Stop"), ("R", "Record"),
            ("Home", "Go to Start"), ("End", "Go to End"),
            ("P", "Piano Roll"), ("T / Ctrl+T", "Timeline"),
            ("B", "Drum Machine"), ("F", "Effects Rack"),
            ("D", "Split Selected Track"), ("F2", "Rename Selected Track"),
            ("C", "Change Track Color"), ("Delete", "Delete Selected Track"),
            ("Ctrl+Z", "Undo"), ("Ctrl+Y", "Redo"),
            ("Ctrl+S", "Save Project"), ("Ctrl+O", "Load Project"),
            ("Ctrl+E", "Export Mix (WAV)"), ("L", "Toggle Loop"),
        ]
        listbox = tk.Listbox(keys_frame, bg=BG_TRACK, fg=FG,
                             selectbackground=ACCENT_DIM, selectforeground="#ffffff",
                             font=("Consolas", 10), borderwidth=0, highlightthickness=0)
        listbox.pack(fill="both", expand=True, padx=10, pady=10)
        for key, desc in keys:
            listbox.insert("end", f"{key:<14} - {desc}")

        ttk.Button(win, text="Close", command=win.destroy).pack(anchor="e", padx=14, pady=(0, 12))

    def show_keyboard_commands(self):
        commands = (
            "OpenDAW - Keyboard Commands\n\n"
            "Playback / Transport:\n"
            "Space       Play / Pause\n"
            "S           Stop\n"
            "R           Record\n"
            "Home        Go to Start\n"
            "End         Go to End\n\n"
            "Track Editing:\n"
            "F2          Rename Selected Track\n"
            "C           Change Selected Track Color\n"
            "F           Open Effects Rack\n"
            "D           Split Selected Track at Playhead\n"
            "Delete      Delete Selected Track\n"
            "+ Marker    Add marker at playhead\n\n"
            "View:\n"
            "P           Piano Roll\n"
            "T           Timeline\n"
            "B           Drum Beat Maker\n"
            "Ctrl+T      Timeline\n\n"
            "Project:\n"
            "Ctrl+S      Save Project\n"
            "Ctrl+O      Load Project\n"
            "Ctrl+E      Export Mix (WAV)\n"
            "BPM         Change in the top toolbar"        )
        messagebox.showinfo("Keyboard Commands", commands)

    def _toggle_drum_view_from_shortcut(self, _event=None):
        self._toggle_drum_machine()
        return "break"

    def _toggle_piano_roll(self):
        if self.piano_roll_visible:
            self._show_timeline()
        else:
            self._show_piano_roll()

    # ------------------------------------------------------------
    # Transport bar (dark grey), including record button
    # ------------------------------------------------------------
    def _build_transport(self):
        transport = tk.Frame(self.root, bg=BG_PANEL, height=54)
        transport.pack(side="top", fill="x")
        transport.pack_propagate(False)
        self.transport_bar = transport

        inner = tk.Frame(transport, bg=BG_PANEL)
        inner.pack(pady=8)

        self.play_btn = ttk.Button(inner, text="\u25b6 Play", command=self.play)
        self.play_btn.pack(side="left")
        ttk.Button(inner, text="\u23f8 Pause", command=self.pause).pack(side="left", padx=5)
        ttk.Button(inner, text="\u23f9 Stop", command=self.stop).pack(side="left")
        self.loop_btn = ttk.Button(inner, text="Loop: Off", command=self.toggle_loop)
        self.loop_btn.pack(side="left", padx=(10, 0))
        ttk.Button(inner, text="Set A", command=self.set_loop_start).pack(side="left", padx=(4, 0))
        ttk.Button(inner, text="Set B", command=self.set_loop_end).pack(side="left", padx=(4, 0))

        # --- record button: red circle ---
        self.record_canvas = tk.Canvas(inner, width=30, height=30, bg=BG_PANEL, highlightthickness=0)
        self.record_canvas.pack(side="left", padx=(14, 4))
        self.record_oval = self.record_canvas.create_oval(4, 4, 26, 26, fill=RECORD_RED, outline="")
        self.record_canvas.bind("<Button-1>", lambda e: self.toggle_recording())
        self.record_canvas.tag_bind(self.record_oval, "<Button-1>", lambda e: self.toggle_recording())

        self.record_status_label = tk.Label(inner, text="", bg=BG_PANEL, fg=RECORD_RED)
        self.record_status_label.pack(side="left", padx=(0, 10))

        self.time_label = tk.Label(inner, text="00:00 / 00:00", bg=BG_PANEL, fg=FG)
        self.time_label.pack(side="left", padx=10)

        self.progress = ttk.Progressbar(inner, orient="horizontal", length=280, mode="determinate")
        self.progress.pack(side="left", padx=10)

    # ------------------------------------------------------------
    # Track handling
    # ------------------------------------------------------------
    def add_track(self):
        path = filedialog.askopenfilename(
            title="Choose an audio file",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        if not path:
            return
        self._add_new_track(path)

    def _add_new_track(self, path: str, initial_volume=100.0, initial_muted=False, initial_solo=False,
                       trim_start=None, trim_end=None, initial_name=None, initial_color=None,
                       initial_start_frame=0):
        if not self._restoring_history:
            self._push_undo()
        try:
            next_color = TRACK_COLORS[len(self.engine.tracks) % len(TRACK_COLORS)]
            track = Track(path, name=initial_name, color=initial_color or next_color)
        except Exception as e:
            messagebox.showerror("Couldn't load track", str(e))
            return None

        track.volume = initial_volume / 100.0
        track.start_frame = max(0, int(initial_start_frame or 0))
        if trim_start is not None and trim_end is not None:
            track.set_trim(trim_start, trim_end)

        self.engine.add_track(track)
        self.empty_label.pack_forget()
        self._add_track_row(track, initial_volume=initial_volume,
                             initial_muted=initial_muted, initial_solo=initial_solo)
        self._recompute_timeline()
        return track

    def select_track(self, track, row=None):
        if track not in self.engine.tracks:
            return
        self.selected_track = track
        if row is None:
            row = self.track_rows.get(track)
        for t, r in self.track_rows.items():
            border = "#ffffff" if t is track else t.color
            r.configure(highlightbackground=border, highlightcolor=border)
            r.configure(highlightthickness=2 if t is track else 1)
        self._update_left_panel()

    def _update_left_panel(self):
        if not hasattr(self, "left_tracks_label"):
            return
        count = len(self.engine.tracks)
        total = self.engine.total_frames()
        bpm = getattr(self, "bpm_var", None)
        bpm_value = bpm.get() if bpm is not None else 120
        self.left_tracks_label.config(text=f"Tracks: {count}")
        self.left_length_label.config(text=f"Length: {self._format_time(total, self.engine.sample_rate)}")
        self.left_bpm_label.config(text=f"BPM: {bpm_value}")

        track = self.selected_track
        if track is None or track not in self.engine.tracks:
            self.left_selected_label.config(text="None")
            self.left_position_label.config(text="Position: 00:00")
            self.left_duration_label.config(text="Length: 00:00")
            return

        position = track.start_frame / self.engine.sample_rate if self.engine.sample_rate else 0
        duration = track.trimmed_frames / track.sample_rate if track.sample_rate else 0
        self.left_selected_label.config(text=track.name)
        self.left_position_label.config(text=f"Position: {self._format_time(int(position * self.engine.sample_rate), self.engine.sample_rate)}")
        self.left_duration_label.config(text=f"Length: {self._format_time(int(duration * self.engine.sample_rate), self.engine.sample_rate)}")

    def split_selected_track(self):
        self._push_undo()
        track = self.selected_track
        if track is None or track not in self.engine.tracks:
            messagebox.showinfo(APP_NAME, "Select a track first.")
            return

        playhead = self.engine.position
        clip_start = track.start_frame
        clip_length = self.engine._resampled_length(track)
        local_frame = playhead - clip_start

        if local_frame <= 0 or local_frame >= clip_length:
            messagebox.showinfo(
                APP_NAME,
                "Place the playhead inside the selected track before splitting."
            )
            return

        # Convert the output-rate playhead position into this file's sample frames.
        if track.sample_rate == self.engine.sample_rate:
            split_frame = track.trim_start + int(local_frame)
        else:
            ratio = track.sample_rate / self.engine.sample_rate
            split_frame = track.trim_start + int(round(local_frame * ratio))

        split_frame = max(track.trim_start + 1, min(split_frame, track.trim_end - 1))

        left = self._clone_track_segment(
            track, track.trim_start, split_frame, track.start_frame,
            f"{track.name} (1)"
        )
        left_len = self.engine._resampled_length(left)
        right = self._clone_track_segment(
            track, split_frame, track.trim_end, track.start_frame + left_len,
            f"{track.name} (2)"
        )

        # Preserve the original track's relative order.
        with self.engine._lock:
            index = self.engine.tracks.index(track)
            self.engine.tracks[index:index + 1] = [left, right]

        self._rebuild_track_rows()
        self.select_track(left)
        self._recompute_timeline()

    @staticmethod
    def _clone_track_segment(source, trim_start, trim_end, start_frame, name):
        clone = object.__new__(Track)
        clone.file_path = source.file_path
        clone.name = name
        clone.color = source.color
        clone.data = source.data
        clone.sample_rate = source.sample_rate
        clone.volume = source.volume
        clone.muted = source.muted
        clone.solo = source.solo
        clone.start_frame = max(0, int(start_frame))
        clone.trim_start = int(trim_start)
        clone.trim_end = int(trim_end)
        clone.fade_in = min(source.fade_in, max(0, clone.trim_end - clone.trim_start) / clone.sample_rate)
        clone.fade_out = min(source.fade_out, max(0, clone.trim_end - clone.trim_start) / clone.sample_rate)
        clone.effects = dict(source.effects)
        clone._processed_cache = None
        return clone

    def _rebuild_track_rows(self):
        for child in list(self.track_frame.winfo_children()):
            if child is not self.empty_label:
                child.destroy()
        self.track_rows.clear()
        self.track_name_labels.clear()
        self.track_canvases.clear()
        if not self.engine.tracks:
            self.empty_label.pack(pady=20, anchor="w")
            self._update_left_panel()
            return
        self.empty_label.pack_forget()
        for track in self.engine.tracks:
            self._add_track_row(
                track,
                initial_volume=track.volume * 100,
                initial_muted=track.muted,
                initial_solo=track.solo,
            )
        self._update_left_panel()

    def rename_selected_track(self):
        track = self.selected_track
        if track is None or track not in self.engine.tracks:
            messagebox.showinfo(APP_NAME, "Select a track first.")
            return

        new_name = simpledialog.askstring(
            "Rename Track", "Track name:", initialvalue=track.name, parent=self.root
        )
        if new_name is None:
            return
        new_name = new_name.strip()
        if new_name != track.name:
            self._push_undo()
        if not new_name:
            return
        track.name = new_name
        label = self.track_name_labels.get(track)
        if label is not None:
            label.config(text=new_name)

    def cycle_selected_track_color(self):
        track = self.selected_track
        if track is None or track not in self.engine.tracks:
            messagebox.showinfo(APP_NAME, "Select a track first.")
            return

        self._push_undo()
        try:
            current_index = TRACK_COLORS.index(track.color)
        except ValueError:
            current_index = -1
        track.color = TRACK_COLORS[(current_index + 1) % len(TRACK_COLORS)]

        row = self.track_rows.get(track)
        if row is not None:
            row.configure(
                highlightbackground="#ffffff" if track is self.selected_track else track.color,
                highlightcolor="#ffffff" if track is self.selected_track else track.color
            )
        self._redraw_waveform(self.track_canvases[track], track)

    def remove_selected_track(self):
        track = self.selected_track
        if track is None or track not in self.engine.tracks:
            return
        self.remove_track(track)

    def remove_track(self, track):
        self._push_undo()
        row = self.track_rows.pop(track, None)
        self.track_name_labels.pop(track, None)
        self.engine.remove_track(track)
        self.track_canvases.pop(track, None)
        if row is not None:
            row.destroy()
        if self.selected_track is track:
            self.selected_track = self.engine.tracks[-1] if self.engine.tracks else None
            if self.selected_track is not None:
                self.select_track(self.selected_track)
        if not self.engine.tracks:
            self.empty_label.pack(pady=20, anchor="w")
        self._recompute_timeline()
        self._update_left_panel()

    def _add_track_row(self, track: Track, initial_volume=100.0, initial_muted=False, initial_solo=False):
        row = tk.Frame(
            self.track_frame, bg=BG_TRACK,
            highlightbackground=track.color, highlightcolor=track.color,
            highlightthickness=1
        )
        row.pack(fill="x", pady=4, padx=2, anchor="w")
        self.track_rows[track] = row

        row.bind("<Button-1>", lambda _e, t=track, r=row: self.select_track(t, r))

        # --- top line: name + controls ---
        top = tk.Frame(row, bg=BG_TRACK)
        top.pack(fill="x", padx=6, pady=(4, 2), anchor="w")
        top.bind("<Button-1>", lambda _e, t=track, r=row: self.select_track(t, r))

        name_label = tk.Label(
            top, text=track.name, width=16, anchor="w",
            bg=BG_TRACK, fg=FG, cursor="hand2"
        )
        name_label.pack(side="left")
        name_label.bind("<Button-1>", lambda _e, t=track, r=row: self.select_track(t, r))
        name_label.bind("<Double-Button-1>", lambda _e: self.rename_selected_track())
        self.track_name_labels[track] = name_label

        vol_var = tk.DoubleVar(value=initial_volume)

        def on_vol(val, t=track):
            t.volume = float(val) / 100.0

        ttk.Scale(
            top, from_=0, to=100, variable=vol_var, command=on_vol,
            orient="horizontal", length=100
        ).pack(side="left", padx=6)

        tk.Label(top, text="Pan", bg=BG_TRACK, fg=FG_DIM).pack(side="left", padx=(3, 1))
        pan_var = tk.DoubleVar(value=getattr(track, "pan", 0.0) * 100.0)
        def on_pan(val, t=track):
            t.pan = max(-1.0, min(1.0, float(val) / 100.0))
        tk.Scale(top, from_=-100, to=100, variable=pan_var, resolution=1,
                 orient="horizontal", length=80, showvalue=False,
                 bg=BG_TRACK, fg=FG, troughcolor=BG_PANEL,
                 highlightthickness=0, activebackground=ACCENT, sliderlength=12
                 ).pack(side="left", padx=(0, 5))

        mute_var = tk.BooleanVar(value=initial_muted)
        track.muted = initial_muted

        def toggle_mute(t=track, mv=mute_var):
            t.muted = mv.get()
            self.select_track(t)

        ttk.Checkbutton(top, text="Mute", variable=mute_var, command=toggle_mute).pack(side="left", padx=4)

        solo_var = tk.BooleanVar(value=initial_solo)
        track.solo = initial_solo

        def toggle_solo(t=track, sv=solo_var):
            t.solo = sv.get()
            self.select_track(t)

        ttk.Checkbutton(top, text="Solo", variable=solo_var, command=toggle_solo).pack(side="left", padx=4)

        def reset_trim(t=track):
            self.select_track(t)
            t.set_trim(0, t.num_frames)
            self._redraw_waveform(self.track_canvases[t], t)

        ttk.Button(top, text="Reset Trim", command=reset_trim).pack(side="left", padx=4)
        ttk.Button(top, text="Fade In", command=lambda t=track: (self.select_track(t), self.set_clip_fade(t, "in"))).pack(side="left", padx=4)
        ttk.Button(top, text="Fade Out", command=lambda t=track: (self.select_track(t), self.set_clip_fade(t, "out"))).pack(side="left", padx=4)
        ttk.Button(top, text="Rename", command=lambda t=track: (self.select_track(t), self.rename_selected_track())).pack(side="left", padx=4)
        ttk.Button(top, text="Color", command=lambda t=track: (self.select_track(t), self.cycle_selected_track_color())).pack(side="left", padx=4)
        ttk.Button(top, text="FX", command=lambda t=track: (self.select_track(t), self.open_effects_rack(t))).pack(side="left", padx=4)
        ttk.Button(top, text="Remove", command=lambda t=track: self.remove_track(t)).pack(side="left", padx=4)

        # --- bottom line: waveform with shared timeline scale + drag-to-trim handles ---
        wave_canvas = tk.Canvas(
            row, width=TIMELINE_WIDTH, height=WAVEFORM_HEIGHT,
            bg=BG, highlightthickness=0
        )
        wave_canvas.pack(padx=6, pady=(2, 6), anchor="w")

        wave_canvas.bind(
            "<ButtonPress-1>",
            lambda e, t=track, c=wave_canvas: self._on_wave_press(e, t, c)
        )
        wave_canvas.bind(
            "<B1-Motion>",
            lambda e, t=track, c=wave_canvas: self._on_wave_drag(e, t, c)
        )
        wave_canvas.bind("<ButtonRelease-1>", lambda e: self._on_wave_release(e))

        self.track_canvases[track] = wave_canvas
        self._redraw_waveform(wave_canvas, track)
        self.select_track(track)

    # ------------------------------------------------------------
    # Shared timeline scale
    # ------------------------------------------------------------
    def _recompute_timeline(self):
        self._normalize_loop()
        if self.engine.tracks:
            longest = max(t.start_frame / self.engine.sample_rate + t.duration_seconds for t in self.engine.tracks)
        else:
            longest = 0
        basis = max(longest, MIN_TIMELINE_SECONDS)
        self.timeline_basis_seconds = basis
        self.pixels_per_second = TIMELINE_WIDTH / basis

        self._draw_ruler()
        for track, canvas in self.track_canvases.items():
            self._redraw_waveform(canvas, track)

    def _tick_interval(self) -> int:
        for interval in TICK_INTERVALS:
            if interval * self.pixels_per_second >= 50:
                return interval
        return TICK_INTERVALS[-1]

    def _tick_positions(self):
        interval = self._tick_interval()
        t = 0
        ticks = []
        while t <= self.timeline_basis_seconds:
            x = t * self.pixels_per_second
            m, s = divmod(int(t), 60)
            ticks.append((x, f"{m}:{s:02d}"))
            t += interval
        return ticks

    def _draw_ruler(self):
        self.ruler_canvas.delete("all")
        self.ruler_canvas.create_line(0, RULER_HEIGHT - 1, TIMELINE_WIDTH, RULER_HEIGHT - 1,
                                       fill=ACCENT_DIM)
        for x, label in self._tick_positions():
            self.ruler_canvas.create_line(x, RULER_HEIGHT - 8, x, RULER_HEIGHT - 1, fill=ACCENT_DIM)
            self.ruler_canvas.create_text(x + 3, 4, text=label, fill=FG_DIM,
                                           anchor="nw", font=("Segoe UI", 7))

        for marker in self.markers:
            seconds = marker["frame"] / self.engine.sample_rate if self.engine.sample_rate else 0.0
            if 0 <= seconds <= self.timeline_basis_seconds:
                x = seconds * self.pixels_per_second
                self.ruler_canvas.create_line(x, 0, x, RULER_HEIGHT, fill="#ffffff", dash=(3, 2))
                self.ruler_canvas.create_text(x + 3, 2, text=marker["name"], anchor="nw",
                                               fill=ACCENT, font=("Segoe UI", 7, "bold"))

    # ------------------------------------------------------------
    # Waveform drawing + trim handle dragging / clip moving
    # ------------------------------------------------------------
    def _track_start_x(self, track: Track) -> float:
        return (track.start_frame / self.engine.sample_rate) * self.pixels_per_second

    def _frame_to_x(self, frame, track: Track) -> float:
        if track.sample_rate == 0:
            return 0
        return self._track_start_x(track) + (frame / track.sample_rate) * self.pixels_per_second

    def _x_to_frame(self, x, track: Track) -> int:
        local_x = x - self._track_start_x(track)
        seconds = local_x / self.pixels_per_second if self.pixels_per_second else 0
        frame = int(seconds * track.sample_rate)
        return max(0, min(frame, track.num_frames))

    def _redraw_waveform(self, canvas: tk.Canvas, track: Track):
        canvas.delete("all")
        for x, _label in self._tick_positions():
            canvas.create_line(x, 0, x, WAVEFORM_HEIGHT, fill=GRID_LINE)

        track_start_x = self._track_start_x(track)
        track_width_px = max(1, int(track.duration_seconds * self.pixels_per_second))
        visible_start = max(0, int(track_start_x))
        visible_end = min(TIMELINE_WIDTH, int(track_start_x + track_width_px))
        if visible_end <= visible_start:
            return

        visible_width = max(1, visible_end - visible_start)
        mins, maxs = track.get_waveform_peaks(visible_width)
        mid = WAVEFORM_HEIGHT / 2
        for i in range(len(mins)):
            x = visible_start + i
            y1 = mid - maxs[i] * mid
            y2 = mid - mins[i] * mid
            if y1 == y2:
                y1 -= 0.5
                y2 += 0.5
            canvas.create_line(x, y1, x, y2, fill=track.color, tags="waveform")

        x_start = self._frame_to_x(track.trim_start, track)
        x_end = self._frame_to_x(track.trim_end, track)

        if x_start > track_start_x:
            canvas.create_rectangle(track_start_x, 0, x_start, WAVEFORM_HEIGHT, fill=BG, stipple="gray50", outline="", tags="trim_overlay")
        if x_end < track_start_x + track_width_px:
            canvas.create_rectangle(x_end, 0, min(track_start_x + track_width_px, TIMELINE_WIDTH), WAVEFORM_HEIGHT, fill=BG, stipple="gray50", outline="", tags="trim_overlay")

        if track.fade_in > 0:
            fade_x = x_start + min(x_end - x_start, track.fade_in * self.pixels_per_second)
            canvas.create_line(x_start, WAVEFORM_HEIGHT - 2, fade_x, 2, fill="#ffffff", dash=(2, 2), tags="fade")
        if track.fade_out > 0:
            fade_x = x_end - min(x_end - x_start, track.fade_out * self.pixels_per_second)
            canvas.create_line(fade_x, 2, x_end, WAVEFORM_HEIGHT - 2, fill="#ffffff", dash=(2, 2), tags="fade")

        canvas.create_rectangle(x_start - 2, 0, x_start + 2, WAVEFORM_HEIGHT, fill="#ffffff", outline="", tags="handle")
        canvas.create_rectangle(x_end - 2, 0, x_end + 2, WAVEFORM_HEIGHT, fill="#ffffff", outline="", tags="handle")

    def _on_wave_press(self, event, track: Track, canvas: tk.Canvas):
        self.select_track(track)
        x_start = self._frame_to_x(track.trim_start, track)
        x_end = self._frame_to_x(track.trim_end, track)
        track_start_x = self._track_start_x(track)

        if abs(event.x - x_start) <= HANDLE_TOLERANCE:
            self._push_undo()
            handle = "start"
        elif abs(event.x - x_end) <= HANDLE_TOLERANCE:
            self._push_undo()
            handle = "end"
        elif track_start_x <= event.x <= x_end:
            self._push_undo()
            self._drag_state = {"track": track, "canvas": canvas, "handle": "move", "mouse_x": event.x, "original_start": track.start_frame}
            return
        else:
            self._drag_state = {"track": None, "canvas": None, "handle": None}
            return
        self._drag_state = {"track": track, "canvas": canvas, "handle": handle}

    def _on_wave_drag(self, event, track: Track, canvas: tk.Canvas):
        if self._drag_state.get("track") is not track:
            return
        handle = self._drag_state.get("handle")
        if handle == "move":
            delta_x = event.x - self._drag_state["mouse_x"]
            delta_frames = int(round((delta_x / self.pixels_per_second) * self.engine.sample_rate))
            track.start_frame = max(0, self._drag_state["original_start"] + delta_frames)
            self._recompute_timeline()
            return
        if handle not in ("start", "end"):
            return
        frame = self._x_to_frame(event.x, track)
        if handle == "start":
            track.trim_start = max(0, min(frame, track.trim_end - 1))
        else:
            track.trim_end = min(track.num_frames, max(frame, track.trim_start + 1))
        self._recompute_timeline()

    def _on_wave_release(self, event):
        self._drag_state = {"track": None, "canvas": None, "handle": None}

    # ------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------
    def _on_master_vol(self, val):
        self.engine.master_volume = float(val) / 100.0

    def play(self):
        if not self.engine.tracks:
            messagebox.showinfo(APP_NAME, "Add at least one track first.")
            return
        self.engine.play()

    def pause(self):
        self.engine.pause()

    def stop(self):
        self.engine.stop()

    def _toggle_play_pause(self):
        if self.engine.playing:
            self.pause()
        else:
            self.play()

    # ------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------
    def toggle_recording(self):
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _populate_input_devices(self):
        try:
            devices = sd.query_devices()
            self.input_device_indices = []
            self.input_device_names = []
            for idx, dev in enumerate(devices):
                if int(dev.get("max_input_channels", 0)) > 0:
                    self.input_device_indices.append(idx)
                    self.input_device_names.append(str(dev.get("name", f"Input {idx}")))
            if not self.input_device_names:
                self.input_device_indices = [None]
                self.input_device_names = ["Default Input"]
        except Exception:
            self.input_device_indices = [None]
            self.input_device_names = ["Default Input"]
        self.input_device_menu["values"] = self.input_device_names
        self.input_device_menu.current(0)

    def _selected_input_device(self):
        i = self.input_device_menu.current() if hasattr(self, "input_device_menu") else -1
        return self.input_device_indices[i] if 0 <= i < len(self.input_device_indices) else None

    def _update_input_meter(self):
        if hasattr(self, "input_meter"):
            self.input_meter["value"] = min(1.0, max(0.0, self.input_peak))
        self.input_peak *= 0.8
        self.root.after(50, self._update_input_meter)

    def _start_recording(self):
        self._record_buffers = []
        self.record_start_frame = int(self.engine.position)
        self.input_peak = 0.0
        try:
            kwargs = dict(samplerate=self.engine.sample_rate, channels=1, dtype="float32",
                          callback=self._record_callback)
            device = self._selected_input_device()
            if device is not None:
                kwargs["device"] = device
            self._record_stream = sd.InputStream(**kwargs)
            self._record_stream.start()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't start recording:\n{e}")
            self._record_stream = None
            return
        self.recording = True
        self.record_status_label.config(text="VOCAL REC")
        self._blink_record()

    def _record_callback(self, indata, frames, time_info, status):
        self._record_buffers.append(indata.copy())
        try:
            self.input_peak = max(self.input_peak, float(np.max(np.abs(indata))))
        except Exception:
            pass

    def _blink_record(self):
        if not self.recording:
            return
        current = self.record_canvas.itemcget(self.record_oval, "fill")
        new_color = RECORD_RED_DIM if current == RECORD_RED else RECORD_RED
        self.record_canvas.itemconfig(self.record_oval, fill=new_color)
        self.root.after(500, self._blink_record)

    def _stop_recording(self):
        self.recording = False
        self.record_canvas.itemconfig(self.record_oval, fill=RECORD_RED)
        self.record_status_label.config(text="")

        if self._record_stream is not None:
            self._record_stream.stop()
            self._record_stream.close()
            self._record_stream = None

        if not self._record_buffers:
            return

        data = np.concatenate(self._record_buffers, axis=0)
        self._record_buffers = []

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_dir = os.getcwd()

        recordings_dir = os.path.join(script_dir, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)

        filename = f"recording_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        path = os.path.join(recordings_dir, filename)

        try:
            sf.write(path, data, self.engine.sample_rate)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't save recording:\n{e}")
            return

        self._add_new_track(
            path,
            initial_name=f"Vocal Take {len(self.engine.tracks) + 1}",
            initial_start_frame=self.record_start_frame,
        )

    # ------------------------------------------------------------
    # Markers / fades / auto-save
    # ------------------------------------------------------------
    def add_marker(self):
        total = self.engine.total_frames()
        frame = max(0, min(int(self.engine.position), total if total else int(self.engine.position)))
        name = simpledialog.askstring("Add Marker", "Marker name:",
                                       initialvalue=f"Marker {len(self.markers) + 1}", parent=self.root)
        if not name:
            return
        self._push_undo()
        self.markers.append({"frame": frame, "name": name.strip()})
        self.markers.sort(key=lambda m: m["frame"])
        self._draw_ruler()

    def set_clip_fade(self, track, kind):
        current = track.fade_in if kind == "in" else track.fade_out
        label = "Fade In" if kind == "in" else "Fade Out"
        value = simpledialog.askfloat(label, "Duration in seconds:", initialvalue=round(current, 2),
                                      minvalue=0.0, parent=self.root)
        if value is None:
            return
        self._push_undo()
        max_duration = track.trimmed_frames / track.sample_rate if track.sample_rate else 0.0
        value = min(float(value), max_duration)
        if kind == "in":
            track.fade_in = value
        else:
            track.fade_out = value
        self._redraw_waveform(self.track_canvases[track], track)

    def toggle_autosave(self):
        self.autosave_enabled = not self.autosave_enabled
        self.autosave_btn.config(text="Auto-save: On" if self.autosave_enabled else "Auto-save: Off")

    def _autosave_tick(self):
        try:
            if self.autosave_enabled:
                self._write_autosave()
        except Exception:
            pass
        self.root.after(AUTOSAVE_INTERVAL_MS, self._autosave_tick)

    def _write_autosave(self):
        if not self.engine.tracks and not self.piano_notes and not any(self.drum_pattern.values()):
            return
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_dir = os.getcwd()
        path = os.path.join(script_dir, "opendaw_autosave.json")
        data = {
            "master_volume": self.master_vol.get(),
            "bpm": int(self.bpm_var.get()),
            "tracks": [{
                "file_path": t.file_path, "name": t.name, "volume": t.volume,
                "muted": t.muted, "solo": t.solo, "pan": getattr(t, "pan", 0.0), "trim_start": t.trim_start,
                "trim_end": t.trim_end, "color": t.color, "start_frame": t.start_frame,
                "fade_in": t.fade_in, "fade_out": t.fade_out, "effects": t.effects,
            } for t in self.engine.tracks],
            "piano_notes": [[m, b] for m, b in sorted(self.piano_notes)],
            "piano_instrument": self.piano_instrument.get(),
            "drum_pattern": {row: sorted(steps) for row, steps in self.drum_pattern.items()},
            "loop_enabled": self.loop_enabled, "loop_start": self.loop_start, "loop_end": self.loop_end,
            "markers": self.markers,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------
    # Save / Load / Export
    # ------------------------------------------------------------
    def save_project(self):
        if not self.engine.tracks:
            messagebox.showinfo(APP_NAME, "No tracks to save.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Project", defaultextension=".json",
            filetypes=[(f"{APP_NAME} Project", "*.json")],
        )
        if not path:
            return
        self.project_path = path

        data = {
            "master_volume": self.master_vol.get(),
            "bpm": int(self.bpm_var.get()),
            "tracks": [
                {
                    "file_path": t.file_path,
                    "name": t.name,
                    "volume": t.volume,
                    "muted": t.muted,
                    "solo": t.solo,
                    "pan": getattr(t, "pan", 0.0),
                    "trim_start": t.trim_start,
                    "trim_end": t.trim_end,
                    "color": t.color,
                    "start_frame": t.start_frame,
                    "fade_in": t.fade_in,
                    "fade_out": t.fade_out,
                    "effects": t.effects,
                }
                for t in self.engine.tracks
            ],
            "piano_notes": [[midi, beat] for midi, beat in sorted(self.piano_notes)],
            "piano_instrument": self.piano_instrument.get(),
            "drum_pattern": {row: sorted(steps) for row, steps in self.drum_pattern.items()},
            "loop_enabled": self.loop_enabled,
            "loop_start": self.loop_start,
            "loop_end": self.loop_end,
            "markers": self.markers,
        }

        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return

        messagebox.showinfo(APP_NAME, "Project saved.")

    def _load_autosave_json(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_dir = os.getcwd()
        path = os.path.join(script_dir, "opendaw_autosave.json")
        if not os.path.exists(path):
            messagebox.showinfo(APP_NAME, "No auto-save file found yet.")
            return
        if messagebox.askyesno(APP_NAME, "Recover the latest auto-save? Your current session will be replaced."):
            self.load_project(path)

    def load_project(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
            title="Load Project", filetypes=[(f"{APP_NAME} Project", "*.json")]
        )
        if not path:
            return
        self.project_path = path

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return

        # clear current session
        for child in list(self.track_frame.winfo_children()):
            if child is not self.empty_label:
                child.destroy()
        self.engine.tracks.clear()
        self.track_canvases.clear()
        self.track_rows.clear()
        self.track_name_labels.clear()
        self.selected_track = None
        self.piano_notes = {tuple(note) for note in data.get("piano_notes", []) if len(note) == 2}
        saved_instrument = data.get("piano_instrument", "Piano")
        self.piano_instrument.set(saved_instrument if saved_instrument in ("Piano", "Guitar") else "Piano")
        saved_drums = data.get("drum_pattern", {})
        self.drum_pattern = {row: set(saved_drums.get(row, [])) for row in DRUM_ROWS}

        master_vol = data.get("master_volume", 100)
        self.master_vol.set(master_vol)
        self.engine.master_volume = master_vol / 100.0
        try:
            self.bpm_var.set(max(40, min(240, int(data.get("bpm", 120)))))
        except (TypeError, ValueError):
            self.bpm_var.set(120)
        self.loop_enabled = bool(data.get("loop_enabled", False))
        self.loop_start = int(data.get("loop_start", 0) or 0)
        self.loop_end = int(data.get("loop_end", 0) or 0)
        self._update_loop_button()

        skipped = []
        for td in data.get("tracks", []):
            fp = td.get("file_path", "")
            if not os.path.exists(fp):
                skipped.append(fp)
                continue

            track = self._add_new_track(
                fp,
                initial_volume=td.get("volume", 1.0) * 100,
                initial_muted=td.get("muted", False),
                initial_solo=td.get("solo", False),
                trim_start=td.get("trim_start"),
                trim_end=td.get("trim_end"),
                initial_name=td.get("name"),
                initial_color=td.get("color"),
                initial_start_frame=td.get("start_frame", 0),
            )
            if track is None:
                skipped.append(fp)
                continue
            try:
                track.pan = max(-1.0, min(1.0, float(td.get("pan", 0.0) or 0.0)))
            except (TypeError, ValueError):
                track.pan = 0.0
            saved_effects = td.get("effects", {})
            if isinstance(saved_effects, dict):
                for key in track.effects:
                    if key in saved_effects:
                        try:
                            track.effects[key] = float(saved_effects[key])
                        except (TypeError, ValueError):
                            pass
                track.fade_in = max(0.0, float(td.get("fade_in", 0.0) or 0.0))
                track.fade_out = max(0.0, float(td.get("fade_out", 0.0) or 0.0))
                track.invalidate_effect_cache()

        self.markers = [dict(m) for m in data.get("markers", [])
                        if isinstance(m, dict) and "frame" in m and "name" in m]
        self._draw_ruler()

        if not self.engine.tracks:
            self.empty_label.pack(pady=20, anchor="w")
        self._draw_piano_roll()
        self._refresh_drum_buttons()
        self._last_history_signature = self._state_signature(self._capture_state())

        if skipped:
            messagebox.showwarning(
                APP_NAME,
                "Loaded, but couldn't find/read:\n" + "\n".join(skipped),
            )
        else:
            messagebox.showinfo(APP_NAME, "Project loaded.")

    def export_mix(self):
        if not self.engine.tracks:
            messagebox.showinfo(APP_NAME, "Add at least one track first.")
            return

        path = filedialog.asksaveasfilename(
            title="Export Mix", defaultextension=".wav",
            filetypes=[("WAV file", "*.wav")],
        )
        if not path:
            return

        try:
            self.engine.export_mix(path)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return

        messagebox.showinfo(APP_NAME, f"Mix exported to {os.path.basename(path)}")

    # ------------------------------------------------------------
    # Playhead / progress update loop
    # ------------------------------------------------------------
    @staticmethod
    def _format_time(frames: int, sample_rate: int) -> str:
        secs = frames / sample_rate if sample_rate else 0
        m, s = divmod(int(secs), 60)
        return f"{m:02d}:{s:02d}"

    def _playhead_x_for_track(self, track: Track) -> float:
        local_position = self.engine.position - track.start_frame
        if local_position < 0:
            return -1
        if track.sample_rate == self.engine.sample_rate:
            frame_in_trim = local_position
        else:
            ratio = track.sample_rate / self.engine.sample_rate
            frame_in_trim = local_position * ratio
        return self._frame_to_x(track.trim_start + frame_in_trim, track)

    def _update_loop(self):
        total = self.engine.total_frames()
        pos = min(self.engine.position, total) if total else 0
        sr = self.engine.sample_rate

        self.progress["value"] = (pos / total) * 100 if total else 0
        self.time_label.config(
            text=f"{self._format_time(pos, sr)} / {self._format_time(total, sr)}"
        )
        self._update_left_panel()

        for track, canvas in self.track_canvases.items():
            x = self._playhead_x_for_track(track)
            canvas.delete("playhead")
            if 0 <= x <= TIMELINE_WIDTH:
                canvas.create_line(x, 0, x, WAVEFORM_HEIGHT, fill="#ffffff", tags="playhead")

        self.root.after(100, self._update_loop)


# ======================================================================
# Entry point
# ======================================================================
def main():
    root = tk.Tk()
    app = DawApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
