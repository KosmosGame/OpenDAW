from .shared import *
from .track import Track
from .audio_engine import AudioEngine
from .core import CoreMixin
from .plugin_chord import PluginChordMixin
from .mixer_mastering import MixerMasteringMixin
from .piano_drum import PianoDrumMixin
from .timeline_edit import TimelineEditMixin
from .project import ProjectMixin
from .transport import TransportMixin
from .settings import SettingsMixin
class DawApp(CoreMixin, PluginChordMixin, MixerMasteringMixin, PianoDrumMixin,
             TimelineEditMixin, ProjectMixin, TransportMixin, SettingsMixin):
    pass
