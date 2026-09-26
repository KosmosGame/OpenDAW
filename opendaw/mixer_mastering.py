from .shared import *
from .track import Track
from .audio_engine import AudioEngine
class MixerMasteringMixin:
        def open_mixer(self):
            if getattr(self, "mixer_window", None) is not None:
                try:
                    if self.mixer_window.winfo_exists():
                        self.mixer_window.lift()
                        return
                except Exception:
                    pass
            win = tk.Toplevel(self.root)
            self.mixer_window = win
            win.title("OpenDAW Mixer")
            win.geometry("900x520")
            win.minsize(650, 420)
            win.configure(bg=BG)
            header = tk.Frame(win, bg=BG_PANEL, height=44)
            header.pack(fill="x")
            header.pack_propagate(False)
            tk.Label(header, text="MIXER", bg=BG_PANEL, fg=ACCENT,
                     font=("Segoe UI", 13, "bold")).pack(side="left", padx=14)
            tk.Label(header, text="Track volume, pan, mute and solo",
                     bg=BG_PANEL, fg=FG_DIM).pack(side="left", padx=8)
            outer = tk.Frame(win, bg=BG)
            outer.pack(fill="both", expand=True, padx=10, pady=10)
            canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
            hscroll = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
            canvas.configure(xscrollcommand=hscroll.set)
            canvas.pack(fill="both", expand=True)
            hscroll.pack(fill="x")
            strip_frame = tk.Frame(canvas, bg=BG)
            canvas.create_window((0, 0), window=strip_frame, anchor="nw")
            strip_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            def sync_track(track, kind, value):
                try:
                    if kind == "volume":
                        track.volume = max(0.0, min(1.5, float(value)))
                    elif kind == "pan":
                        track.pan = max(-1.0, min(1.0, float(value)))
                    self._update_left_panel()
                except Exception:
                    pass
            for idx, track in enumerate(self.engine.tracks):
                strip = tk.Frame(strip_frame, bg=BG_PANEL, width=120, height=390,
                                 highlightbackground=track.color, highlightthickness=2)
                strip.grid(row=0, column=idx, padx=5, sticky="n")
                strip.grid_propagate(False)
                tk.Label(strip, text=track.name[:16], bg=BG_PANEL, fg=FG,
                         font=("Segoe UI", 9, "bold")).pack(pady=(10, 4))
                tk.Label(strip, text="VOL", bg=BG_PANEL, fg=FG_DIM).pack()
                vol = tk.DoubleVar(value=float(track.volume) * 100.0)
                tk.Scale(strip, from_=150, to=0, orient="vertical", variable=vol,
                         command=lambda v, t=track: sync_track(t, "volume", float(v) / 100.0),
                         bg=BG_PANEL, fg=FG, troughcolor=BG, highlightthickness=0,
                         activebackground=ACCENT, length=190).pack(pady=3)
                tk.Label(strip, text="PAN", bg=BG_PANEL, fg=FG_DIM).pack()
                pan = tk.DoubleVar(value=float(getattr(track, "pan", 0.0)))
                tk.Scale(strip, from_=-1, to=1, resolution=0.01, orient="horizontal",
                         variable=pan,
                         command=lambda v, t=track: sync_track(t, "pan", v),
                         bg=BG_PANEL, fg=FG, troughcolor=BG,
                         highlightthickness=0, activebackground=ACCENT,
                         length=100).pack()
                tk.Label(strip, text="L     C     R", bg=BG_PANEL, fg=FG_DIM).pack()
                mute = tk.BooleanVar(value=track.muted)
                solo = tk.BooleanVar(value=track.solo)
                ttk.Checkbutton(strip, text="Mute", variable=mute,
                                command=lambda t=track, v=mute: setattr(t, "muted", v.get())).pack(pady=(8, 1))
                ttk.Checkbutton(strip, text="Solo", variable=solo,
                                command=lambda t=track, v=solo: setattr(t, "solo", v.get())).pack()
            master = tk.Frame(strip_frame, bg=BG_PANEL, width=140, height=390,
                              highlightbackground=ACCENT, highlightthickness=2)
            master.grid(row=0, column=len(self.engine.tracks), padx=(16, 5), sticky="n")
            master.grid_propagate(False)
            tk.Label(master, text="MASTER", bg=BG_PANEL, fg=ACCENT,
                     font=("Segoe UI", 10, "bold")).pack(pady=(10, 4))
            tk.Label(master, text="VOLUME", bg=BG_PANEL, fg=FG_DIM).pack()
            mvol = tk.DoubleVar(value=float(self.engine.master_volume) * 100.0)
            def change_master(v):
                self.engine.master_volume = max(0.0, min(1.5, float(v) / 100.0))
                if hasattr(self, "master_vol"):
                    self.master_vol.set(float(v))
            tk.Scale(master, from_=150, to=0, orient="vertical", variable=mvol,
                     command=change_master, bg=BG_PANEL, fg=FG, troughcolor=BG,
                     highlightthickness=0, activebackground=ACCENT, length=220).pack(pady=4)
            tk.Label(master, text="OUTPUT", bg=BG_PANEL, fg=FG_DIM).pack()
            tk.Label(master, text="100%", bg=BG_PANEL, fg=FG,
                     font=("Segoe UI", 11, "bold")).pack(pady=6)
            ttk.Button(master, text="Close", command=win.destroy).pack(side="bottom", pady=14)
            def on_close():
                self.mixer_window = None
                win.destroy()
            win.protocol("WM_DELETE_WINDOW", on_close)
        def open_mastering(self):
            win = tk.Toplevel(self.root)
            win.title("OpenDAW Mastering Studio")
            win.geometry("520x440")
            win.configure(bg=BG_PANEL)
            tk.Label(win, text="MASTERING STUDIO", bg=BG_PANEL, fg=ACCENT,
                     font=("Segoe UI", 14, "bold")).pack(pady=(14, 4))
            tk.Label(win, text="Final processing applied to the master output and exports.",
                     bg=BG_PANEL, fg=FG_DIM).pack(pady=(0, 14))
            vars_ = {}
            controls = [("Low", "low", -12, 12, " dB"), ("Mid", "mid", -12, 12, " dB"),
                        ("High", "high", -12, 12, " dB"), ("Compressor", "compressor", 0, 100, "%"),
                        ("Saturation", "saturation", 0, 100, "%"), ("Limiter", "limiter", 0.4, 1.0, "") ]
            for label, key, lo, hi, suffix in controls:
                row = tk.Frame(win, bg=BG_PANEL)
                row.pack(fill="x", padx=24, pady=7)
                tk.Label(row, text=label, width=14, anchor="w", bg=BG_PANEL, fg=FG).pack(side="left")
                initial = float(self.engine.master_fx.get(key, 0.0))
                if key in ("compressor", "saturation"):
                    initial *= 100.0
                var = tk.DoubleVar(value=initial)
                vars_[key] = var
                value_label = tk.Label(row, text="", width=8, anchor="e", bg=BG_PANEL, fg=FG_DIM)
                value_label.pack(side="right")
                def changed(_v=None, k=key, v=var, vl=value_label, sfx=suffix):
                    val = float(v.get())
                    if k in ("compressor", "saturation"):
                        self.engine.master_fx[k] = val / 100.0
                        vl.config(text=f"{val:.0f}{sfx}")
                    else:
                        self.engine.master_fx[k] = val
                        vl.config(text=f"{val:.1f}{sfx}")
                scale = ttk.Scale(row, from_=lo, to=hi, variable=var, command=changed)
                scale.pack(side="left", fill="x", expand=True, padx=8)
                changed()
            def reset():
                self._push_undo()
                defaults = {"low":0.0,"mid":0.0,"high":0.0,"compressor":0.0,"limiter":0.85,"saturation":0.0}
                self.engine.master_fx.update(defaults)
                for k,v in vars_.items():
                    x = defaults[k] * (100.0 if k in ("compressor", "saturation") else 1.0)
                    v.set(x)
            bar = tk.Frame(win, bg=BG_PANEL)
            bar.pack(fill="x", padx=24, pady=18)
            ttk.Button(bar, text="Reset", command=reset).pack(side="left")
            ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
