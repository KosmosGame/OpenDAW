from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class SettingsMixin:
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
            self.root.bind_all("<KeyPress-x>", self._shortcut_delete_piano_note)
            self.root.bind_all("<Control-s>", self._shortcut_save)
            self.root.bind_all("<Control-o>", self._shortcut_load)
            self.root.bind_all("<Control-e>", self._shortcut_export)
            self.root.bind_all("<KeyPress-plus>", lambda _e: self.adjust_zoom(ZOOM_STEP))
            self.root.bind_all("<KeyPress-equal>", lambda _e: self.adjust_zoom(ZOOM_STEP))
            self.root.bind_all("<KeyPress-minus>", lambda _e: self.adjust_zoom(-ZOOM_STEP))
            self.root.bind_all("<KeyPress-0>", lambda _e: self.fit_timeline())
            self.root.bind_all("<Control-t>", self._shortcut_timeline)
            self.root.bind_all("<Control-z>", self._shortcut_undo)
            self.root.bind_all("<Control-y>", self._shortcut_redo)
            self.root.bind_all("<KeyPress-l>", self._shortcut_loop)
            self.root.bind_all("<KeyPress-m>", self._shortcut_midi_record)
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
        def _shortcut_delete_piano_note(self, _event=None):
            if self._typing_widget(self.root.focus_get()): return
            self.delete_selected_piano_note(); return "break"
        def _shortcut_save(self, _event=None):
            if self._typing_widget(self.root.focus_get()): return
            self.save_project(); return "break"
        def _shortcut_load(self, _event=None):
            if self._typing_widget(self.root.focus_get()): return
            self.load_project(); return "break"
        def _shortcut_export(self, _event=None):
            if self._typing_widget(self.root.focus_get()): return
            self.export_mix(); return "break"
        def _shortcut_midi_record(self, _event=None):
            if self._typing_widget(self.root.focus_get()): return
            if not self.piano_roll_visible:
                self._show_piano_roll()
            self.toggle_midi_recording(); return "break"
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
    ("P", "Piano Roll"), ("T / Ctrl+T", "Timeline"), ("M", "MIDI Record"), ("X", "Delete Selected MIDI Note"),
                ("B", "Drum Machine"), ("F", "Effects Rack"), ("M", "MIDI Record"),
                ("D", "Split Selected Track"), ("X", "Delete Selected MIDI Note"), ("F2", "Rename Selected Track"),
                ("C", "Change Track Color"), ("Delete", "Delete Selected Track"),
                ("Ctrl+Z", "Undo"), ("Ctrl+Y", "Redo"),
                ("Ctrl+S", "Save Project"), ("Ctrl+O", "Load Project"),
                ("Ctrl+E", "Export Mix (WAV)"), ("L", "Toggle Loop"), ("X", "Delete Selected MIDI Note"),
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
                "M           MIDI Record (Piano Roll)\n"
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
