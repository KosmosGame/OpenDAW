from .shared import *
from .track import Track
class AudioEngine:
    def __init__(self, sample_rate: int = 44100, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self.tracks = []
        self.position = 0
        self.playing = False
        self.master_volume = 1.0
        self.master_fx = {"low": 0.0, "mid": 0.0, "high": 0.0, "compressor": 0.0, "limiter": 0.85, "saturation": 0.0}
        self._stream = None
        self._lock = threading.Lock()
        self.loop_enabled = False
        self.loop_start = 0
        self.loop_end = 0
    def add_track(self, track):
        with self._lock:
            self.tracks.append(track)
    def remove_track(self, track):
        with self._lock:
            if track in self.tracks:
                self.tracks.remove(track)
    def total_frames(self) -> int:
        with self._lock:
            if not self.tracks:
                return 0
            return max(t.start_frame + self._resampled_length(t) for t in self.tracks)
    def _resampled_length(self, track) -> int:
        frames = track.trimmed_frames
        if track.sample_rate == self.sample_rate:
            return frames
        ratio = self.sample_rate / track.sample_rate
        return int(round(frames * ratio))
    def _track_slice(self, track, start: int, end: int) -> np.ndarray:
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
    def _process_master(self, mix):
        if mix.size == 0:
            return mix
        out = mix.astype(np.float32, copy=True)
        fx = self.master_fx
        low_gain = float(fx.get("low", 0.0))
        mid_gain = float(fx.get("mid", 0.0))
        high_gain = float(fx.get("high", 0.0))
        if abs(low_gain) + abs(mid_gain) + abs(high_gain) > 1e-4:
            sr = float(self.sample_rate)
            low_fc = 180.0
            high_fc = 4500.0
            a_low = (2.0 * np.pi * low_fc / sr) / (1.0 + 2.0 * np.pi * low_fc / sr)
            a_high = (2.0 * np.pi * high_fc / sr) / (1.0 + 2.0 * np.pi * high_fc / sr)
            low = np.zeros_like(out)
            prev = np.zeros(out.shape[1], dtype=np.float32)
            for i in range(len(out)):
                prev = prev + a_low * (out[i] - prev)
                low[i] = prev
            high = np.zeros_like(out)
            hp_prev = np.zeros(out.shape[1], dtype=np.float32)
            for i in range(len(out)):
                hp_prev = hp_prev + a_high * (out[i] - hp_prev)
                high[i] = out[i] - hp_prev
            mid = out - low - high
            out = (low * (10.0 ** (low_gain / 20.0)) +
                   mid * (10.0 ** (mid_gain / 20.0)) +
                   high * (10.0 ** (high_gain / 20.0)))
        comp = max(0.0, min(1.0, float(fx.get("compressor", 0.0))))
        if comp > 0.001:
            threshold = 0.78 - comp * 0.35
            ratio = 1.8 + comp * 6.0
            mag = np.abs(out)
            over = mag > threshold
            gain = np.ones_like(mag)
            gain[over] = (threshold + (mag[over] - threshold) / ratio) / np.maximum(mag[over], 1e-8)
            out *= gain
        sat = max(0.0, min(1.0, float(fx.get("saturation", 0.0))))
        if sat > 0.001:
            drive = 1.0 + sat * 5.0
            shaped = np.tanh(out * drive) / np.tanh(drive)
            out = out * (1.0 - sat * 0.35) + shaped * (sat * 0.35)
        limiter = max(0.10, min(1.0, float(fx.get("limiter", 0.85))))
        out = np.tanh(out / limiter) * limiter
        np.clip(out, -1.0, 1.0, out=out)
        return out
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
    def render_mix(self) -> np.ndarray:
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
        mix = self._process_master(mix)
        return mix
    def export_mix(self, file_path: str):
        mix = self.render_mix()
        sf.write(file_path, mix, self.sample_rate)
