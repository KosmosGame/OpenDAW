from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class ProjectMixin:
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
                "master_fx": dict(self.engine.master_fx),
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
                    state["bpm"], tuple((m["frame"], m["name"]) for m in state.get("markers", [])),
                    tuple(sorted(state.get("master_fx", {}).items())))
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
                self.piano_notes = self._normalize_piano_notes(state["piano_notes"])
                self.piano_instrument.set(state["piano_instrument"] if state["piano_instrument"] in ("Piano", "Guitar") else "Piano")
                self.drum_pattern = {k: set(v) for k, v in state.get("drum_pattern", {r: set() for r in DRUM_ROWS}).items()}
                self.bpm_var.set(max(40, min(240, int(state["bpm"]))))
                self.markers = [dict(m) for m in state.get("markers", [])]
                self.engine.master_fx = dict(state.get("master_fx", self.engine.master_fx))
                self.loop_enabled = bool(state["loop_enabled"])
                self.loop_start = int(state["loop_start"])
                self.loop_end = int(state["loop_end"])
                self._sync_loop_to_engine()
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
                "piano_notes": [[m, b, length, velocity] for m, b, length, velocity in sorted(self.piano_notes)],
                "piano_instrument": self.piano_instrument.get(),
                "drum_pattern": {row: sorted(steps) for row, steps in self.drum_pattern.items()},
                "loop_enabled": self.loop_enabled, "loop_start": self.loop_start, "loop_end": self.loop_end,
                "markers": self.markers,
                "master_fx": dict(self.engine.master_fx),
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
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
                "piano_notes": [[midi, beat, length, velocity] for midi, beat, length, velocity in sorted(self.piano_notes)],
                "piano_instrument": self.piano_instrument.get(),
                "drum_pattern": {row: sorted(steps) for row, steps in self.drum_pattern.items()},
                "loop_enabled": self.loop_enabled,
                "loop_start": self.loop_start,
                "loop_end": self.loop_end,
                "markers": self.markers,
                "master_fx": dict(self.engine.master_fx),
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
            for child in list(self.track_frame.winfo_children()):
                if child is not self.empty_label:
                    child.destroy()
            self.engine.tracks.clear()
            self.track_canvases.clear()
            self.track_rows.clear()
            self.track_name_labels.clear()
            self.selected_track = None
            self.piano_notes = self._normalize_piano_notes(data.get("piano_notes", []))
            saved_instrument = data.get("piano_instrument", "Piano")
            self.piano_instrument.set(saved_instrument if saved_instrument in ("Piano", "Guitar") else "Piano")
            saved_drums = data.get("drum_pattern", {})
            self.drum_pattern = {row: set(saved_drums.get(row, [])) for row in DRUM_ROWS}
            master_vol = data.get("master_volume", 100)
            self.master_vol.set(master_vol)
            self.engine.master_volume = master_vol / 100.0
            saved_master_fx = data.get("master_fx", {})
            if isinstance(saved_master_fx, dict):
                for key in self.engine.master_fx:
                    if key in saved_master_fx:
                        try:
                            self.engine.master_fx[key] = float(saved_master_fx[key])
                        except (TypeError, ValueError):
                            pass
            try:
                self.bpm_var.set(max(40, min(240, int(data.get("bpm", 120)))))
            except (TypeError, ValueError):
                self.bpm_var.set(120)
            self.loop_enabled = bool(data.get("loop_enabled", False))
            self.loop_start = int(data.get("loop_start", 0) or 0)
            self.loop_end = int(data.get("loop_end", 0) or 0)
            self._sync_loop_to_engine()
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
