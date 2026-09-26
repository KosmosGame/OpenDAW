from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class TransportMixin:
        def _on_bpm_changed(self):
            if not self._restoring_history:
                self._push_undo()
            try:
                bpm = int(self.bpm_var.get())
            except (TypeError, ValueError):
                bpm = 120
            self.bpm_var.set(max(40, min(240, bpm)))
            self._update_left_panel()
        def _sync_loop_to_engine(self):
            self.engine.loop_enabled = bool(self.loop_enabled)
            self.engine.loop_start = int(self.loop_start)
            self.engine.loop_end = int(self.loop_end)
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
            self._sync_loop_to_engine()
            self._sync_loop_to_engine()
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
            self._sync_loop_to_engine()
            self._update_left_panel()
        def set_loop_end(self):
            total = self.engine.total_frames()
            if total <= 0:
                return
            self.loop_end = max(1, min(self.engine.position, total))
            if self.loop_end <= self.loop_start:
                self.loop_start = 0
            self._sync_loop_to_engine()
            self._update_left_panel()
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
        @staticmethod
        def _format_time(frames: int, sample_rate: int) -> str:
            secs = frames / sample_rate if sample_rate else 0
            minutes, seconds = divmod(int(secs), 60)
            return f"{minutes:02d}:{seconds:02d}"
        def _playhead_x_for_track(self, track):
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
            if hasattr(self, "progress"):
                self.progress["value"] = (pos / total) * 100 if total else 0
            if hasattr(self, "time_label"):
                self.time_label.config(
                    text=f"{self._format_time(pos, sr)} / {self._format_time(total, sr)}"
                )
            if hasattr(self, "_update_left_panel"):
                self._update_left_panel()
            for track, canvas in getattr(self, "track_canvases", {}).items():
                try:
                    x = self._playhead_x_for_track(track)
                    canvas.delete("playhead")
                    if 0 <= x <= self.timeline_content_width:
                        canvas.create_line(x, 0, x, WAVEFORM_HEIGHT, fill="#ffffff", tags="playhead")
                except Exception:
                    pass
            self.root.after(100, self._update_loop)
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
