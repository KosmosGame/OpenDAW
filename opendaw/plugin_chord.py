from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class PluginChordMixin:
        def _ensure_plugin_dir(self):
            try:
                os.makedirs(self.plugin_dir, exist_ok=True)
                readme = os.path.join(self.plugin_dir, "README.txt")
                if not os.path.exists(readme):
                    with open(readme, "w", encoding="utf-8") as f:
                        f.write("OpenDAW Python Plugins\n\n"
                                "Create a .py file containing NAME, optional DESCRIPTION, and register(app).\n"
                                "Example:\n\n"
                                "NAME = 'My Plugin'\n"
                                "DESCRIPTION = 'Does something useful'\n\n"
                                "def register(app):\n"
                                "    app.register_plugin_command('Hello', lambda: print('Hello from OpenDAW'))\n")
            except Exception:
                pass
        def register_plugin_command(self, name, callback):
            if not callable(callback):
                raise TypeError("Plugin command callback must be callable")
            self.plugin_commands[str(name)] = callback
        def _load_plugins(self):
            self.loaded_plugins = []
            try:
                files = sorted(Path(self.plugin_dir).glob("*.py"))
            except Exception:
                files = []
            for path in files:
                if path.name.startswith("_"):
                    continue
                try:
                    module_name = "opendaw_plugin_" + path.stem.replace(" ", "_")
                    spec = importlib.util.spec_from_file_location(module_name, str(path))
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    self.loaded_plugins.append({
                        "name": str(getattr(module, "NAME", path.stem)),
                        "description": str(getattr(module, "DESCRIPTION", "")),
                        "file": path.name,
                        "module": module,
                    })
                    register = getattr(module, "register", None)
                    if callable(register):
                        register(self)
                except Exception as e:
                    self.loaded_plugins.append({
                        "name": path.stem + " (error)",
                        "description": str(e),
                        "file": path.name,
                        "module": None,
                    })
        def open_plugin_manager(self):
            win = tk.Toplevel(self.root)
            win.title("OpenDAW Plugins")
            win.geometry("620x430")
            win.configure(bg=BG_PANEL)
            tk.Label(win, text="Plugin Manager", bg=BG_PANEL, fg=FG,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
            tk.Label(win, text=f"Folder: {self.plugin_dir}", bg=BG_PANEL, fg=FG_DIM,
                     wraplength=590, justify="left").pack(anchor="w", padx=14, pady=(0, 8))
            box = tk.Listbox(win, bg=BG_TRACK, fg=FG, selectbackground=ACCENT_DIM,
                             highlightthickness=0, height=14)
            box.pack(fill="both", expand=True, padx=14, pady=8)
            for item in self.loaded_plugins:
                suffix = " — " + item["description"] if item["description"] else ""
                box.insert("end", f"{item['name']}  [{item['file']}]" + suffix)
            if not self.loaded_plugins:
                box.insert("end", "No plugins loaded. Put .py plugins in the plugins folder.")
            buttons = tk.Frame(win, bg=BG_PANEL)
            buttons.pack(fill="x", padx=14, pady=(0, 12))
            ttk.Button(buttons, text="Open Folder", command=lambda: self._open_plugin_folder()).pack(side="left")
            ttk.Button(buttons, text="Reload Plugins", command=lambda: self._reload_plugin_window(win)).pack(side="left", padx=8)
            ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")
        def _open_plugin_folder(self):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(self.plugin_dir)
                elif sys.platform == "darwin":
                    import subprocess; subprocess.Popen(["open", self.plugin_dir])
                else:
                    import subprocess; subprocess.Popen(["xdg-open", self.plugin_dir])
            except Exception:
                messagebox.showinfo(APP_NAME, f"Plugin folder:\n{self.plugin_dir}")
        def _reload_plugin_window(self, old_window=None):
            if old_window is not None:
                old_window.destroy()
            self.plugin_commands.clear()
            self._load_plugins()
            self.open_plugin_manager()
        def open_chord_maker(self):
            win = tk.Toplevel(self.root)
            win.title("Chord Maker")
            win.geometry("430x330")
            win.configure(bg=BG_PANEL)
            win.transient(self.root)
            tk.Label(win, text="Chord Maker", bg=BG_PANEL, fg=FG,
                     font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 10))
            root_var = tk.StringVar(value="C")
            quality_var = tk.StringVar(value="Major")
            octave_var = tk.IntVar(value=4)
            inversion_var = tk.IntVar(value=0)
            length_var = tk.DoubleVar(value=1.0)
            beat_var = tk.DoubleVar(value=max(0.0, self._current_beat_for_editing()))
            fields = [
                ("Root", root_var, ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]),
                ("Chord", quality_var, ["Major", "Minor", "Diminished", "Augmented", "Sus2", "Sus4", "7", "Major 7", "Minor 7"]),
            ]
            for r, (label, var, vals) in enumerate(fields, start=1):
                tk.Label(win, text=label, bg=BG_PANEL, fg=FG).grid(row=r, column=0, sticky="w", padx=14, pady=6)
                cb = ttk.Combobox(win, textvariable=var, values=vals, state="readonly", width=18)
                cb.grid(row=r, column=1, sticky="w", padx=8, pady=6)
            for r, (label, var, vals) in enumerate([
                ("Octave", octave_var, [3, 4, 5]),
                ("Inversion", inversion_var, [0, 1, 2]),
                ("Length (beats)", length_var, [0.25, 0.5, 1.0, 2.0, 4.0]),
            ], start=3):
                tk.Label(win, text=label, bg=BG_PANEL, fg=FG).grid(row=r, column=0, sticky="w", padx=14, pady=6)
                cb = ttk.Combobox(win, textvariable=var, values=vals, state="readonly", width=18)
                cb.grid(row=r, column=1, sticky="w", padx=8, pady=6)
            tk.Label(win, text="Start beat", bg=BG_PANEL, fg=FG).grid(row=6, column=0, sticky="w", padx=14, pady=6)
            tk.Spinbox(win, from_=0, to=PIANO_BEATS - 0.25, increment=0.25, textvariable=beat_var,
                       bg=BG_TRACK, fg=FG, buttonbackground=BG_PANEL, highlightthickness=0, width=19).grid(row=6, column=1, sticky="w", padx=8, pady=6)
            tk.Label(win, text="Adds the chord directly to the Piano Roll.", bg=BG_PANEL, fg=FG_DIM).grid(row=7, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 10))
            def add():
                try:
                    start = float(beat_var.get())
                    length = float(length_var.get())
                    octave = int(octave_var.get())
                    inv = int(inversion_var.get())
                except Exception:
                    messagebox.showerror(APP_NAME, "Invalid chord settings.", parent=win); return
                pitches = self._build_chord_pitches(root_var.get(), quality_var.get(), octave, inv)
                if not pitches:
                    return
                if start >= PIANO_BEATS:
                    messagebox.showinfo(APP_NAME, "Start beat is outside the Piano Roll range.", parent=win); return
                length = max(0.125, min(length, PIANO_BEATS - start))
                self._push_undo()
                self.piano_notes = {n for n in self.piano_notes if not (abs(n[1] - start) < 1e-6 and any(n[0] == p for p in pitches))}
                for pitch in pitches:
                    self.piano_notes.add((int(pitch), float(start), float(length), int(self.piano_velocity.get())))
                self.selected_piano_note = None
                self._draw_piano_roll()
                self._update_history_buttons()
                win.destroy()
                if not self.piano_roll_visible:
                    self._show_piano_roll()
            ttk.Button(win, text="Add Chord", command=add).grid(row=8, column=0, columnspan=2, pady=(0, 14))
        def _current_beat_for_editing(self):
            bpm = max(40.0, float(self.bpm_var.get()))
            return (self.engine.position / self.engine.sample_rate) / (60.0 / bpm) if self.engine.sample_rate else 0.0
        @staticmethod
        def _build_chord_pitches(root_name, quality, octave, inversion):
            roots = {"C":0,"C#":1,"D":2,"D#":3,"E":4,"F":5,"F#":6,"G":7,"G#":8,"A":9,"A#":10,"B":11}
            intervals = {
                "Major": [0,4,7], "Minor": [0,3,7], "Diminished": [0,3,6],
                "Augmented": [0,4,8], "Sus2": [0,2,7], "Sus4": [0,5,7],
                "7": [0,4,7,10], "Major 7": [0,4,7,11], "Minor 7": [0,3,7,10],
            }
            if root_name not in roots or quality not in intervals:
                return []
            pitches = [12 * (int(octave) + 1) + roots[root_name] + i for i in intervals[quality]]
            inversion = max(0, min(int(inversion), len(pitches) - 1))
            for _ in range(inversion):
                pitches[0] += 12
                pitches.sort()
            return [p for p in pitches if 0 <= p <= 127]
