from .shared import *
class Track:
    def __init__(self, file_path: str, name: str = None, color: str = None):
        self.file_path = file_path
        self.name = name or os.path.basename(file_path)
        self.color = color or TRACK_COLORS[0]
        data, sample_rate = sf.read(file_path, dtype="float32", always_2d=True)
        self.data = data
        self.sample_rate = sample_rate
        self.volume = 1.0
        self.muted = False
        self.solo = False
        self.pan = 0.0
        self.start_frame = 0
        self.trim_start = 0
        self.trim_end = self.num_frames
        self.fade_in = 0.0
        self.fade_out = 0.0
        self.effects = {
            "gain": 0.0,
            "delay": 0.0,
            "delay_time": 0.25,
            "reverb": 0.0,
            "distortion": 0.0,
            "compressor": 0.0,
            "lowpass": 20000.0,
            "highpass": 20.0,
        }
        self._processed_cache = None
    @property
    def num_frames(self) -> int:
        return self.data.shape[0]
    @property
    def channels(self) -> int:
        return self.data.shape[1]
    @property
    def duration_seconds(self) -> float:
        if self.sample_rate == 0:
            return 0.0
        return self.num_frames / self.sample_rate
    @property
    def trimmed_frames(self) -> int:
        return max(0, self.trim_end - self.trim_start)
    def set_trim(self, start, end):
        start = max(0, min(int(start), self.num_frames))
        end = max(0, min(int(end), self.num_frames))
        if end <= start:
            end = min(self.num_frames, start + 1)
        self.trim_start = start
        self.trim_end = end
    def get_waveform_peaks(self, num_buckets: int):
        num_buckets = max(1, num_buckets)
        mono = self.data.mean(axis=1) if self.channels > 1 else self.data[:, 0]
        n = len(mono)
        if n == 0:
            return np.zeros(num_buckets), np.zeros(num_buckets)
        bucket_size = max(1, n // num_buckets)
        usable = bucket_size * num_buckets
        if usable == 0:
            padded = np.zeros(num_buckets)
            padded[:n] = mono
            return padded, padded
        trimmed = mono[:usable].reshape(num_buckets, bucket_size)
        mins = trimmed.min(axis=1)
        maxs = trimmed.max(axis=1)
        return mins, maxs
    def invalidate_effect_cache(self):
        self._processed_cache = None
    def get_processed_data(self):
        if self._processed_cache is not None:
            return self._processed_cache
        data = self.data.astype(np.float32, copy=True)
        if len(data) == 0:
            self._processed_cache = data
            return data
        gain_db = float(self.effects.get("gain", 0.0))
        if abs(gain_db) > 1e-6:
            data *= float(10.0 ** (gain_db / 20.0))
        sr = float(self.sample_rate or 44100)
        hp = max(20.0, min(float(self.effects.get("highpass", 20.0)), sr * 0.45))
        lp = max(hp + 1.0, min(float(self.effects.get("lowpass", 20000.0)), sr * 0.49))
        if hp > 20.1:
            rc = 1.0 / (2.0 * np.pi * hp)
            alpha = rc / (rc + 1.0 / sr)
            prev_x = np.zeros(data.shape[1], dtype=np.float32)
            prev_y = np.zeros(data.shape[1], dtype=np.float32)
            for i in range(len(data)):
                x = data[i].copy()
                y = alpha * (prev_y + x - prev_x)
                data[i] = y
                prev_x = x
                prev_y = y
        if lp < sr * 0.49:
            rc = 1.0 / (2.0 * np.pi * lp)
            alpha = (1.0 / sr) / (rc + 1.0 / sr)
            prev = data[0].copy()
            for i in range(1, len(data)):
                prev = prev + alpha * (data[i] - prev)
                data[i] = prev
        drive = max(0.0, min(1.0, float(self.effects.get("distortion", 0.0))))
        if drive > 0.001:
            amount = 1.0 + drive * 14.0
            wet = 0.15 + drive * 0.75
            distorted = np.tanh(data * amount)
            data = data * (1.0 - wet) + distorted * wet
        comp = max(0.0, min(1.0, float(self.effects.get("compressor", 0.0))))
        if comp > 0.001:
            threshold = 0.55 - comp * 0.30
            ratio = 2.0 + comp * 8.0
            magnitude = np.abs(data)
            over = magnitude > threshold
            gain = np.ones_like(magnitude)
            gain[over] = (threshold + (magnitude[over] - threshold) / ratio) / np.maximum(magnitude[over], 1e-8)
            data *= gain
        delay_wet = max(0.0, min(1.0, float(self.effects.get("delay", 0.0))))
        if delay_wet > 0.001:
            delay_samples = max(1, int(float(self.effects.get("delay_time", 0.25)) * sr))
            delayed = np.zeros_like(data)
            if delay_samples < len(data):
                delayed[delay_samples:] = data[:-delay_samples]
            data = data * (1.0 - delay_wet) + delayed * delay_wet
        reverb_wet = max(0.0, min(1.0, float(self.effects.get("reverb", 0.0))))
        if reverb_wet > 0.001:
            wet = np.zeros_like(data)
            taps = [(0.031, 0.32), (0.047, 0.22), (0.071, 0.16), (0.113, 0.11)]
            for delay_sec, level in taps:
                d = max(1, int(delay_sec * sr))
                if d < len(data):
                    wet[d:] += data[:-d] * level
            data = data * (1.0 - reverb_wet) + wet * reverb_wet
        np.clip(data, -1.0, 1.0, out=data)
        self._processed_cache = data.astype(np.float32, copy=False)
        return self._processed_cache
    def __repr__(self):
        return f"<Track '{self.name}' {self.duration_seconds:.1f}s vol={self.volume:.2f}>"
