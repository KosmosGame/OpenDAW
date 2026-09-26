from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class TimelineEditMixin:
        def _build_divider(self, horizontal=True):
            if horizontal:
                line = tk.Frame(self.root, bg=DIVIDER, height=2)
                line.pack(side="top", fill="x")
            else:
                return tk.Frame(self.root, bg=DIVIDER, width=2)
        def _build_top_bar(self):
            top_bar = tk.Frame(self.root, bg=BG_PANEL, height=82)
            top_bar.pack(side="top", fill="x")
            top_bar.pack_propagate(False)
            self.top_bar = top_bar
            inner = tk.Frame(top_bar, bg=BG_PANEL)
            inner.pack(side="top", fill="x", padx=10, pady=(5, 2))
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
            ttk.Button(inner, text="Chord Maker", command=self.open_chord_maker).pack(side="left", padx=(8, 0))
            ttk.Button(inner, text="Plugins", command=self.open_plugin_manager).pack(side="left", padx=(8, 0))
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
            ttk.Button(inner, text="Mastering", command=self.open_mastering).pack(side="left", padx=(8, 0))
            ttk.Button(inner, text="Mixer", command=self.open_mixer).pack(side="left", padx=(8, 0))
            controls = tk.Frame(top_bar, bg=BG_PANEL)
            controls.pack(side="top", fill="x", padx=10, pady=(0, 5))
            vol_frame = tk.Frame(controls, bg=BG_PANEL)
            vol_frame.pack(side="left", padx=(24, 0))
            tk.Label(vol_frame, text="Master Volume", bg=BG_PANEL, fg=FG).pack(side="left", padx=(0, 6))
            self.master_vol = tk.DoubleVar(value=100)
            ttk.Scale(
                vol_frame, from_=0, to=100, variable=self.master_vol,
                command=self._on_master_vol, orient="horizontal", length=150
            ).pack(side="left")
            mic_frame = tk.Frame(controls, bg=BG_PANEL)
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
            bpm_frame = tk.Frame(controls, bg=BG_PANEL)
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
            zoom_frame = tk.Frame(controls, bg=BG_PANEL)
            zoom_frame.pack(side="left", padx=(16, 0))
            tk.Label(zoom_frame, text="Zoom", bg=BG_PANEL, fg=FG).pack(side="left", padx=(0, 4))
            ttk.Button(zoom_frame, text="−", width=2, command=lambda: self.adjust_zoom(-ZOOM_STEP)).pack(side="left")
            self.zoom_label = tk.Label(zoom_frame, text="100%", bg=BG_PANEL, fg=FG, width=5)
            self.zoom_label.pack(side="left")
            ttk.Button(zoom_frame, text="+", width=2, command=lambda: self.adjust_zoom(ZOOM_STEP)).pack(side="left")
            ttk.Button(zoom_frame, text="Fit", width=4, command=self.fit_timeline).pack(side="left", padx=(3, 0))
        def adjust_zoom(self, delta):
            new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom_factor + float(delta)))
            if abs(new_zoom - self.zoom_factor) < 1e-9:
                return
            self.zoom_factor = new_zoom
            self._update_zoom_layout()
        def fit_timeline(self):
            self.zoom_factor = 1.0
            self._update_zoom_layout()
        def _update_zoom_layout(self):
            if self.engine.tracks:
                longest = max(t.start_frame / self.engine.sample_rate + t.duration_seconds for t in self.engine.tracks)
            else:
                longest = 0
            basis = max(longest, MIN_TIMELINE_SECONDS)
            self.timeline_basis_seconds = basis
            self.pixels_per_second = (TIMELINE_WIDTH / basis) * self.zoom_factor
            self.timeline_content_width = max(TIMELINE_WIDTH, int(round(basis * self.pixels_per_second)) + 20)
            if hasattr(self, "zoom_label"):
                self.zoom_label.config(text=f"{int(round(self.zoom_factor * 100))}%")
            if hasattr(self, "timeline_canvas"):
                self.timeline_canvas.configure(scrollregion=(0, 0, self.timeline_content_width, self.track_frame.winfo_reqheight()))
            if hasattr(self, "ruler_canvas"):
                self.ruler_canvas.configure(width=max(TIMELINE_WIDTH, min(self.timeline_content_width, self.timeline_view.winfo_width() or TIMELINE_WIDTH)), scrollregion=(0, 0, self.timeline_content_width, RULER_HEIGHT))
            for track, canvas in self.track_canvases.items():
                canvas.configure(width=self.timeline_content_width)
                self._redraw_waveform(canvas, track)
            self._draw_ruler()
        def _build_main_area(self):
            self.main_area = tk.Frame(self.root, bg=BG)
            self.main_area.pack(side="top", fill="both", expand=True)
            self.timeline_view = tk.Frame(self.main_area, bg=BG)
            self.timeline_view.pack(fill="both", expand=True)
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
            tk.Frame(self.timeline_view, bg=DIVIDER, width=2).pack(side="left", fill="y")
            right_area = tk.Frame(self.timeline_view, bg=BG)
            right_area.pack(side="left", fill="both", expand=True, padx=8, pady=8)
            self.ruler_canvas = tk.Canvas(
                right_area, width=TIMELINE_WIDTH, height=RULER_HEIGHT,
                bg=BG, highlightthickness=0
            )
            self.ruler_canvas.pack(side="top", anchor="w", fill="x")
            track_container = tk.Frame(right_area, bg=BG)
            track_container.pack(side="top", fill="both", expand=True, pady=(4, 0))
            canvas = tk.Canvas(track_container, bg=BG, highlightthickness=0)
            self.timeline_canvas = canvas
            vscroll = ttk.Scrollbar(track_container, orient="vertical", command=canvas.yview)
            hscroll = ttk.Scrollbar(right_area, orient="horizontal", command=lambda *args: self._timeline_xview(*args))
            self.track_frame = tk.Frame(canvas, bg=BG)
            self.track_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.create_window((0, 0), window=self.track_frame, anchor="nw")
            canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            vscroll.pack(side="right", fill="y")
            hscroll.pack(side="bottom", fill="x")
            self.empty_label = tk.Label(
                self.track_frame,
                text="No tracks yet — click '+ Add Track' to load a .wav file.",
                bg=BG, fg=FG_DIM,
            )
            self.empty_label.pack(pady=20, anchor="w")
            self._build_piano_roll()
            self._build_drum_machine()
        def _timeline_xview(self, *args):
            self.timeline_canvas.xview(*args)
            first, _last = self.timeline_canvas.xview()
            self.ruler_canvas.xview_moveto(first)
        def _recompute_timeline(self):
            self._normalize_loop()
            self._update_zoom_layout()
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
            self.ruler_canvas.create_line(0, RULER_HEIGHT - 1, self.timeline_content_width, RULER_HEIGHT - 1,
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
            visible_end = min(self.timeline_content_width, int(track_start_x + track_width_px))
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
                canvas.create_rectangle(x_end, 0, min(track_start_x + track_width_px, self.timeline_content_width), WAVEFORM_HEIGHT, fill=BG, stipple="gray50", outline="", tags="trim_overlay")
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
        def _add_track_row(self, track: Track, initial_volume=100.0, initial_muted=False, initial_solo=False):
            row = tk.Frame(
                self.track_frame, bg=BG_TRACK,
                highlightbackground=track.color, highlightcolor=track.color,
                highlightthickness=1
            )
            row.pack(fill="x", pady=4, padx=2, anchor="w")
            self.track_rows[track] = row
            row.bind("<Button-1>", lambda _e, t=track, r=row: self.select_track(t, r))
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
            wave_canvas = tk.Canvas(
                row, width=getattr(self, "timeline_content_width", TIMELINE_WIDTH), height=WAVEFORM_HEIGHT,
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
            with self.engine._lock:
                index = self.engine.tracks.index(track)
                self.engine.tracks[index:index + 1] = [left, right]
            self._rebuild_track_rows()
            self.select_track(left)
            self._recompute_timeline()
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
