import os
import json
import time
import threading
import queue
import importlib.util
import sys
import traceback
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
try:
    import mido
except ImportError:
    mido = None
APP_NAME = "OpenDAW"
BG = "#1e1e1e"
BG_PANEL = "#2a2a2a"
BG_TRACK = "#242424"
FG = "#e0e0e0"
FG_DIM = "#888888"
ACCENT = "#00d9ff"
ACCENT_DIM = "#0090b0"
DIVIDER = "#0090b0"
GRID_LINE = "#3a3a3a"
RECORD_RED = "#ff3333"
RECORD_RED_DIM = "#661111"
WAVEFORM_HEIGHT = 50
TIMELINE_WIDTH = 600
RULER_HEIGHT = 24
MIN_TIMELINE_SECONDS = 10
LEFT_PANEL_WIDTH = 170
HANDLE_TOLERANCE = 6
TICK_INTERVALS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
PIANO_KEY_HEIGHT = 18
PIANO_KEY_WIDTH = 55
PIANO_NOTE_WIDTH = 70
PIANO_OCTAVES = 5
PIANO_LOW_MIDI = 48
PIANO_BEATS = 64
DRUM_STEPS = 16
DRUM_ROWS = ["Kick", "Snare", "Closed Hat", "Open Hat", "Clap"]
AUTOSAVE_INTERVAL_MS = 30000
MAX_UNDO_HISTORY = 100
PLUGIN_DIR_NAME = "plugins"
TRACK_COLORS = [
    "#00d9ff",
    "#ff4d6d",
    "#9b5de5",
    "#00c853",
    "#ffab00",
    "#00b8d4",
    "#f15bb5",
    "#8bc34a",
]
ZOOM_MIN = 0.5
ZOOM_MAX = 4.0
ZOOM_STEP = 0.25
def midi_to_freq(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
