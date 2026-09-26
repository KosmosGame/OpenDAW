from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class PianoDrumMixin:
        @staticmethod
        def _normalize_piano_notes(raw_notes):
            notes = set()
            for raw in raw_notes or []:
                try:
                    if len(raw) == 2:
                        midi, beat = raw
                        length, velocity = 1.0, 100
                    elif len(raw) >= 4:
                        midi, beat, length, velocity = raw[:4]
                    else:
                        continue
                    midi = int(midi)
                    beat = max(0.0, float(beat))
                    length = max(0.0625, float(length))
                    velocity = max(1, min(127, int(velocity)))
                    notes.add((midi, beat, length, velocity))
                except (TypeError, ValueError):
                    continue
            return notes
        def _quantize_step_beats(self):
            return {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25, "1/32": 0.125}.get(
                self.piano_quantize.get(), 0.25
            )
        def _snap_beat(self, beat):
            step = self._quantize_step_beats()
            return max(0.0, round(float(beat) / step) * step)
        def _find_piano_note_at(self, x, y):
            total_rows = PIANO_OCTAVES * 12
            row = int(y // PIANO_KEY_HEIGHT)
            midi = PIANO_LOW_MIDI + total_rows - 1 - row
            if not (PIANO_LOW_MIDI <= midi < PIANO_LOW_MIDI + total_rows):
                return None
            beat_x = x / PIANO_NOTE_WIDTH
            for note in sorted(self.piano_notes, key=lambda n: (n[1], n[0])):
                nmidi, start, length, _velocity = note
                if nmidi == midi and start <= beat_x < start + length:
                    return note
            return None
        def _piano_current_beat(self):
            seconds_per_beat = 60.0 / max(40.0, float(self.bpm_var.get()))
            if self.engine.playing:
                return (self.engine.position / self.engine.sample_rate) / seconds_per_beat
            return self._midi_record_base_beat + (time.monotonic() - self._midi_record_base_time) / seconds_per_beat
        def _preview_midi_note(self, midi):
            try:
                sr = self.engine.sample_rate
                freq = 440.0 * (2.0 ** ((midi - 69) / 12.0))
                duration = 0.35
                t = np.arange(int(sr * duration), dtype=np.float32) / sr
                wave = (
                    0.72 * np.sin(2 * np.pi * freq * t)
                    + 0.18 * np.sin(2 * np.pi * freq * 2 * t)
                    + 0.08 * np.sin(2 * np.pi * freq * 3 * t)
                )
                wave *= np.exp(-t * 8.0) * 0.18
                sd.play(np.column_stack([wave, wave]), sr, blocking=False)
            except Exception:
                pass
        def _build_piano_roll(self):
            self.piano_view = tk.Frame(self.main_area, bg=BG)
            header = tk.Frame(self.piano_view, bg=BG_PANEL, height=74)
            header.pack(side="top", fill="x")
            header.pack_propagate(False)
            title_row = tk.Frame(header, bg=BG_PANEL)
            title_row.pack(side="top", fill="x", pady=(4, 0))
            tk.Label(title_row, text="Piano Roll", bg=BG_PANEL, fg=FG,
                     font=("Segoe UI", 10, "bold")).pack(side="left", padx=(12, 8))
            tk.Label(title_row, text="Instrument", bg=BG_PANEL, fg=FG).pack(side="left")
            self.instrument_menu = tk.OptionMenu(
                title_row, self.piano_instrument, "Piano", "Guitar"
            )
            self.instrument_menu.configure(
                bg=BG_PANEL, fg=ACCENT, activebackground=ACCENT_DIM,
                activeforeground="#ffffff", highlightthickness=1,
                highlightbackground=ACCENT_DIM, highlightcolor=ACCENT,
                relief="flat", bd=0, width=8
            )
            self.instrument_menu["menu"].configure(
                bg=BG_PANEL, fg=FG, activebackground=ACCENT_DIM,
                activeforeground="#ffffff"
            )
            self.instrument_menu.pack(side="left", padx=(4, 10))
            tk.Label(title_row, text="Length", bg=BG_PANEL, fg=FG).pack(side="left")
            self.note_length_menu = ttk.Combobox(
                title_row, textvariable=self.piano_note_length, width=6, state="readonly",
                values=(0.25, 0.5, 1.0, 2.0, 4.0)
            )
            self.note_length_menu.pack(side="left", padx=(4, 8))
            tk.Label(title_row, text="Velocity", bg=BG_PANEL, fg=FG).pack(side="left")
            tk.Scale(
                title_row, from_=1, to=127, orient="horizontal", variable=self.piano_velocity,
                bg=BG_PANEL, fg=FG, troughcolor=BG, highlightthickness=0,
                activebackground=ACCENT, showvalue=True, length=100
            ).pack(side="left", padx=(4, 8))
            tk.Label(title_row, text="Quantize", bg=BG_PANEL, fg=FG).pack(side="left")
            self.quantize_menu = ttk.Combobox(
                title_row, textvariable=self.piano_quantize, width=6, state="readonly",
                values=("1/4", "1/8", "1/16", "1/32")
            )
            self.quantize_menu.pack(side="left", padx=(4, 6))
            ttk.Button(title_row, text="Quantize", command=self.quantize_piano_notes).pack(side="left", padx=2)
            ttk.Button(title_row, text="Clear", command=self.clear_piano_notes).pack(side="left", padx=2)
            tk.Label(title_row, text="Notes: 0", bg=BG_PANEL, fg=FG_DIM).pack(side="left", padx=(8, 0))
            self.piano_note_count_label = title_row.winfo_children()[-1]
            ttk.Button(title_row, text="MIDI Record", command=self.toggle_midi_recording).pack(side="right", padx=4)
            self.midi_record_btn = title_row.winfo_children()[-1]
            ttk.Button(title_row, text="+ Add to Timeline", command=self.add_piano_roll_to_timeline).pack(side="right", padx=6)
            help_row = tk.Frame(header, bg=BG_PANEL)
            help_row.pack(side="bottom", fill="x", pady=(0, 4))
            tk.Label(
                help_row,
                text="Click empty space = add  |  Drag note = move  |  Drag right edge = resize  |  Right-click = delete  |  Click piano key = preview",
                bg=BG_PANEL, fg=FG_DIM
            ).pack(side="left", padx=12)
            body = tk.Frame(self.piano_view, bg=BG)
            body.pack(fill="both", expand=True, padx=8, pady=8)
            self.piano_keys_canvas = tk.Canvas(
                body, width=PIANO_KEY_WIDTH, bg=BG_PANEL,
                highlightthickness=0, yscrollincrement=PIANO_KEY_HEIGHT
            )
            self.piano_keys_canvas.pack(side="left", fill="y")
            piano_center = tk.Frame(body, bg=BG)
            piano_center.pack(side="left", fill="both", expand=True)
            self.piano_canvas = tk.Canvas(piano_center, bg=BG, highlightthickness=0)
            self.piano_canvas.pack(side="top", fill="both", expand=True)
            self.piano_x_scroll = ttk.Scrollbar(
                piano_center, orient="horizontal", command=self.piano_canvas.xview
            )
            self.piano_x_scroll.pack(side="bottom", fill="x")
            self.piano_y_scroll = ttk.Scrollbar(
                body, orient="vertical", command=self._piano_yview
            )
            self.piano_y_scroll.pack(side="right", fill="y")
            self.piano_canvas.configure(
                yscrollcommand=self.piano_y_scroll.set,
                xscrollcommand=self.piano_x_scroll.set
            )
            self.piano_keys_canvas.configure(yscrollcommand=self.piano_y_scroll.set)
            self.piano_canvas.bind("<ButtonPress-1>", self._piano_press)
            self.piano_canvas.bind("<B1-Motion>", self._piano_drag_motion)
            self.piano_canvas.bind("<ButtonRelease-1>", self._piano_release)
            self.piano_canvas.bind("<Button-3>", self._piano_right_click)
            self.piano_keys_canvas.bind("<Button-1>", self._piano_key_click)
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
        def _piano_yview(self, *args):
            self.piano_canvas.yview(*args)
            self.piano_keys_canvas.yview(*args)
        def _update_piano_note_count(self):
            if hasattr(self, "piano_note_count_label"):
                self.piano_note_count_label.config(text=f"Notes: {len(self.piano_notes)}")
        def _draw_piano_roll(self):
            if not hasattr(self, "piano_canvas"):
                return
            total_rows = PIANO_OCTAVES * 12
            total_height = total_rows * PIANO_KEY_HEIGHT
            total_width = PIANO_BEATS * PIANO_NOTE_WIDTH
            self.piano_canvas.delete("all")
            self.piano_keys_canvas.delete("all")
            self.piano_canvas.configure(scrollregion=(0, 0, total_width, total_height))
            self.piano_keys_canvas.configure(scrollregion=(0, 0, PIANO_KEY_WIDTH, total_height))
            black_keys = {1, 3, 6, 8, 10}
            for row in range(total_rows):
                midi = PIANO_LOW_MIDI + total_rows - 1 - row
                y = row * PIANO_KEY_HEIGHT
                is_black = midi % 12 in black_keys
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
            for beat in range(PIANO_BEATS + 1):
                x = beat * PIANO_NOTE_WIDTH
                if beat % 4 == 0:
                    grid_fill = ACCENT_DIM
                    width = 2
                else:
                    grid_fill = GRID_LINE
                    width = 1
                self.piano_canvas.create_line(x, 0, x, total_height, fill=grid_fill, width=width)
            for beat in range(PIANO_BEATS):
                if beat % 4 == 0:
                    self.piano_canvas.create_text(
                        beat * PIANO_NOTE_WIDTH + 4, 4, text=str(beat // 4 + 1),
                        anchor="nw", fill=FG_DIM, font=("Segoe UI", 8)
                    )
            for note in sorted(self.piano_notes, key=lambda n: (n[1], n[0])):
                midi, beat, length, velocity = note
                row = PIANO_LOW_MIDI + total_rows - 1 - midi
                if row < 0 or row >= total_rows:
                    continue
                x1 = beat * PIANO_NOTE_WIDTH + 2
                y1 = row * PIANO_KEY_HEIGHT + 2
                x2 = (beat + length) * PIANO_NOTE_WIDTH - 2
                y2 = (row + 1) * PIANO_KEY_HEIGHT - 2
                selected = (note == self.selected_piano_note)
                fill = "#ffffff" if selected else ACCENT
                outline = ACCENT if selected else "#ffffff"
                self.piano_canvas.create_rectangle(x1, y1, max(x1 + 4, x2), y2, fill=fill, outline=outline, width=2 if selected else 1)
                if x2 - x1 > 34:
                    self.piano_canvas.create_text(
                        x1 + 4, (y1 + y2) / 2,
                        text=f"{self._midi_name(midi)}  {velocity}",
                        anchor="w", fill="#101010", font=("Segoe UI", 7, "bold")
                    )
            self._update_piano_note_count()
        def _midi_name(self, midi):
            names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            return f"{names[midi % 12]}{midi // 12 - 1}"
        def _piano_key_click(self, event):
            y = self.piano_keys_canvas.canvasy(event.y)
            row = int(y // PIANO_KEY_HEIGHT)
            total_rows = PIANO_OCTAVES * 12
            midi = PIANO_LOW_MIDI + total_rows - 1 - row
            if PIANO_LOW_MIDI <= midi < PIANO_LOW_MIDI + total_rows:
                self._preview_midi_note(midi)
        def _piano_press(self, event):
            x = self.piano_canvas.canvasx(event.x)
            y = self.piano_canvas.canvasy(event.y)
            found = self._find_piano_note_at(x, y)
            if found is not None:
                self.selected_piano_note = found
                self._piano_drag = {
                    "mode": "resize" if abs(x - (found[1] + found[2]) * PIANO_NOTE_WIDTH) <= 8 else "move",
                    "note": found,
                    "original": found,
                    "mouse_start_beat": x / PIANO_NOTE_WIDTH,
                }
                self._push_undo()
                self._draw_piano_roll()
                return
            total_rows = PIANO_OCTAVES * 12
            row = int(y // PIANO_KEY_HEIGHT)
            midi = PIANO_LOW_MIDI + total_rows - 1 - row
            if not (0 <= row < total_rows):
                return
            beat = self._snap_beat(x / PIANO_NOTE_WIDTH)
            if beat >= PIANO_BEATS or midi < PIANO_LOW_MIDI or midi >= PIANO_LOW_MIDI + total_rows:
                return
            self._push_undo()
            note = (midi, float(beat), float(self.piano_note_length.get()), int(self.piano_velocity.get()))
            self.piano_notes = {n for n in self.piano_notes if not (n[0] == midi and abs(n[1] - beat) < 1e-6)}
            self.piano_notes.add(note)
            self.selected_piano_note = note
            self._preview_midi_note(midi)
            self._draw_piano_roll()
        def _piano_drag_motion(self, event):
            drag = self._piano_drag
            if not drag.get("mode") or drag.get("note") is None:
                return
            x = self.piano_canvas.canvasx(event.x)
            original = drag["original"]
            midi, start, length, velocity = original
            beat = self._snap_beat(x / PIANO_NOTE_WIDTH)
            self.piano_notes.discard(drag["note"])
            if drag["mode"] == "move":
                step = self._quantize_step_beats()
                raw_delta = (x / PIANO_NOTE_WIDTH) - drag["mouse_start_beat"]
                delta = round(raw_delta / step) * step
                new_start = max(0.0, start + delta)
                new_start = min(new_start, max(0.0, PIANO_BEATS - length))
                new_note = (midi, new_start, length, velocity)
            else:
                new_length = max(0.125, beat - start)
                new_length = min(new_length, PIANO_BEATS - start)
                new_note = (midi, start, new_length, velocity)
            self.piano_notes.add(new_note)
            drag["note"] = new_note
            self.selected_piano_note = new_note
            self._draw_piano_roll()
        def _piano_release(self, event):
            self._piano_drag = {"mode": None, "note": None, "original": None}
        def _piano_right_click(self, event):
            x = self.piano_canvas.canvasx(event.x)
            y = self.piano_canvas.canvasy(event.y)
            found = self._find_piano_note_at(x, y)
            if found is not None:
                self._push_undo()
                self.piano_notes.remove(found)
                if self.selected_piano_note == found:
                    self.selected_piano_note = None
                self._draw_piano_roll()
            return "break"
        def delete_selected_piano_note(self):
            if self.selected_piano_note in self.piano_notes:
                self._push_undo()
                self.piano_notes.remove(self.selected_piano_note)
                self.selected_piano_note = None
                self._draw_piano_roll()
        def clear_piano_notes(self):
            if not self.piano_notes:
                return
            self._push_undo()
            self.piano_notes.clear()
            self.selected_piano_note = None
            self._draw_piano_roll()
        def quantize_piano_notes(self):
            if not self.piano_notes:
                return
            self._push_undo()
            step = self._quantize_step_beats()
            quantized = set()
            for midi, beat, length, velocity in self.piano_notes:
                new_beat = max(0.0, min(PIANO_BEATS - length, round(beat / step) * step))
                quantized.add((midi, new_beat, length, velocity))
            self.piano_notes = quantized
            self.selected_piano_note = None
            self._draw_piano_roll()
        def _midi_worker(self):
            try:
                while not self._midi_stop_event.is_set() and self._midi_port is not None:
                    for msg in self._midi_port.iter_pending():
                        self._midi_queue.put(msg)
                    time.sleep(0.005)
            except Exception:
                pass
        def _process_midi_queue(self):
            if self.midi_recording:
                while True:
                    try:
                        msg = self._midi_queue.get_nowait()
                    except queue.Empty:
                        break
                    if getattr(msg, "type", None) not in ("note_on", "note_off"):
                        continue
                    now_beat = self._piano_current_beat()
                    key = (getattr(msg, "channel", 0), getattr(msg, "note", -1))
                    if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
                        if key in self._midi_note_starts:
                            self._midi_note_starts.pop(key, None)
                        self._midi_note_starts[key] = (self._snap_beat(now_beat), int(msg.velocity))
                        self._preview_midi_note(int(msg.note))
                    else:
                        started = self._midi_note_starts.pop(key, None)
                        if started is not None:
                            start_beat, velocity = started
                            length = max(0.125, self._snap_beat(now_beat) - start_beat)
                            if length <= 0.125:
                                length = 0.125
                            note = (int(msg.note), start_beat, min(length, PIANO_BEATS - start_beat), velocity)
                            if note[1] < PIANO_BEATS:
                                self._push_undo()
                                self.piano_notes = {n for n in self.piano_notes if not (n[0] == note[0] and abs(n[1] - note[1]) < 1e-6)}
                                self.piano_notes.add(note)
                                self.selected_piano_note = note
                                self._draw_piano_roll()
            self.root.after(20, self._process_midi_queue)
        def toggle_midi_recording(self):
            if self.midi_recording:
                self._stop_midi_recording()
            else:
                self._start_midi_recording()
        def _start_midi_recording(self):
            if mido is None:
                messagebox.showinfo(APP_NAME, "Install MIDI support first: pip install mido python-rtmidi")
                return
            name = self.midi_input_name
            if not name or name == "No MIDI Input":
                messagebox.showinfo(APP_NAME, "Select a MIDI input in Settings first.")
                return
            try:
                self._midi_port = mido.open_input(name)
            except Exception as e:
                messagebox.showerror(APP_NAME, f"Couldn't open MIDI input:\n{e}")
                return
            self._midi_queue = queue.Queue()
            self._midi_note_starts.clear()
            self._midi_stop_event.clear()
            self._midi_record_base_beat = (self.engine.position / self.engine.sample_rate) / (60.0 / max(40.0, float(self.bpm_var.get())))
            self._midi_record_base_time = time.monotonic()
            self.midi_recording = True
            self.midi_record_btn.config(text="Stop MIDI")
            self._midi_thread = threading.Thread(target=self._midi_worker, daemon=True)
            self._midi_thread.start()
        def _stop_midi_recording(self):
            self.midi_recording = False
            self._midi_stop_event.set()
            if self._midi_port is not None:
                try:
                    self._midi_port.close()
                except Exception:
                    pass
            self._midi_port = None
            if self._midi_thread is not None:
                self._midi_thread.join(timeout=0.2)
                self._midi_thread = None
            self.midi_record_btn.config(text="MIDI Record")
            self._midi_note_starts.clear()
        def add_piano_roll_to_timeline(self):
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
            bpm = max(40.0, min(240.0, float(self.bpm_var.get())))
            seconds_per_beat = 60.0 / bpm
            max_end_beat = max(beat + length for _midi, beat, length, _velocity in self.piano_notes)
            total_seconds = max(1.0, max_end_beat * seconds_per_beat + 0.25)
            total_frames = int(np.ceil(total_seconds * self.engine.sample_rate))
            audio = np.zeros((total_frames, 2), dtype=np.float32)
            rng = np.random.default_rng(12345)
            for midi, beat, length_beats, velocity in sorted(self.piano_notes):
                freq = 440.0 * (2.0 ** ((midi - 69) / 12.0))
                start = int(round(beat * seconds_per_beat * self.engine.sample_rate))
                note_seconds = max(0.06, length_beats * seconds_per_beat)
                length_frames = int(round(note_seconds * self.engine.sample_rate))
                end = min(total_frames, start + length_frames)
                if start >= end:
                    continue
                n = end - start
                t = np.arange(n, dtype=np.float32) / self.engine.sample_rate
                vel = float(velocity) / 127.0
                if self.piano_instrument.get() == "Guitar":
                    body = (
                        0.72 * np.sin(2 * np.pi * freq * t)
                        + 0.20 * np.sin(2 * np.pi * freq * 2 * t)
                        + 0.06 * np.sin(2 * np.pi * freq * 3 * t)
                    )
                    pluck = rng.normal(0.0, 1.0, n).astype(np.float32)
                    pluck *= np.exp(-t * 28.0)
                    envelope = np.exp(-t * max(2.0, 4.0 / max(note_seconds, 0.08)))
                    wave = (0.76 * body + 0.24 * pluck) * envelope * 0.18 * vel
                else:
                    body = (
                        0.70 * np.sin(2 * np.pi * freq * t)
                        + 0.20 * np.sin(2 * np.pi * freq * 2 * t)
                        + 0.10 * np.sin(2 * np.pi * freq * 3 * t)
                    )
                    attack = min(n, max(1, int(0.008 * self.engine.sample_rate)))
                    release = min(n, max(1, int(min(0.18, note_seconds * 0.25) * self.engine.sample_rate)))
                    envelope = np.exp(-t * max(1.2, 2.8 / max(note_seconds, 0.08)))
                    envelope[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)
                    if release > 1:
                        envelope[-release:] *= np.linspace(1.0, 0.0, release, dtype=np.float32)
                    wave = body * envelope * 0.20 * vel
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
