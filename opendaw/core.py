from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class CoreMixin:
        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title(APP_NAME)
            self.root.geometry("900x600")
            self.root.minsize(700, 450)
            self.root.configure(bg=BG)
            self._apply_dark_theme()
            self.engine = AudioEngine()
            self.track_canvases = {}
            self.track_rows = {}
            self.track_name_labels = {}
            self._drag_state = {"track": None, "canvas": None, "handle": None}
            self.selected_track = None
            self.pixels_per_second = TIMELINE_WIDTH / MIN_TIMELINE_SECONDS
            self.timeline_basis_seconds = MIN_TIMELINE_SECONDS
            self.zoom_factor = 1.0
            self.timeline_content_width = TIMELINE_WIDTH
            self.recording = False
            self._record_stream = None
            self._record_buffers = []
            self.record_start_frame = 0
            self.input_peak = 0.0
            self.input_device_indices = []
            self.input_device_names = []
            self.midi_input_name = "No MIDI Input"
            self.midi_input_names = []
            self._undo_stack = []
            self._redo_stack = []
            self._restoring_history = False
            self._last_history_signature = None
            self.markers = []
            self.autosave_enabled = True
            self.project_path = None
            self.loop_enabled = False
            self.loop_start = 0
            self.loop_end = 0
            self.piano_roll_visible = False
            self.piano_notes = set()
            self.piano_instrument = tk.StringVar(value="Piano")
            self.piano_note_length = tk.DoubleVar(value=1.0)
            self.piano_velocity = tk.IntVar(value=100)
            self.piano_quantize = tk.StringVar(value="1/4")
            self.piano_octave_shift = 0
            self.selected_piano_note = None
            self._piano_drag = {"mode": None, "note": None, "original": None}
            self.midi_recording = False
            self._midi_port = None
            self._midi_thread = None
            self._midi_stop_event = threading.Event()
            self._midi_queue = queue.Queue()
            self._midi_note_starts = {}
            self._midi_record_base_beat = 0.0
            self._midi_record_base_time = 0.0
            self.drum_machine_visible = False
            self.drum_pattern = {row: set() for row in DRUM_ROWS}
            self.plugin_commands = {}
            self.loaded_plugins = []
            self.plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), PLUGIN_DIR_NAME)
            self._ensure_plugin_dir()
            self._load_plugins()
            self._build_top_bar()
            self._build_divider(horizontal=True)
            self._build_main_area()
            self._build_divider(horizontal=True)
            self._build_transport()
            self._bind_shortcuts()
            self._draw_ruler()
            self._update_loop()
            self._update_input_meter()
            self._process_midi_queue()
            self._update_history_buttons()
            self._update_loop_button()
            self._last_history_signature = self._state_signature(self._capture_state())
            self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
            self.root.after(AUTOSAVE_INTERVAL_MS, self._autosave_tick)
        def _on_app_close(self):
            if self.midi_recording:
                self._stop_midi_recording()
            try:
                if getattr(self, "_record_stream", None) is not None:
                    self._record_stream.stop()
                    self._record_stream.close()
            except Exception:
                pass
            self.root.destroy()
        def _apply_dark_theme(self):
            style = ttk.Style()
            style.theme_use("clam")
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
