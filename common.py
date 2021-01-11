
from models import Series, Channel, Video

from copy import copy
from dataclasses import dataclass, field
import time
from typing import List, Dict

@dataclass
class Cost():
    value: int = 0

    def add(self,  other: int):
        self.value += other
        return self.value

@dataclass
class Context:
    """A dataclass of convenience fields, useful for branching contexts."""
    api_key: str = ''
    config: Dict = None
    cost: Cost  = field(default_factory=Cost)
    quota: int = None
    series: Series = None
    series_config: Dict = None
    channel: Channel = None
    channels: List[str] = field(default_factory=list)
    now: int = field(default_factory=lambda: int(time.time()))

    def copy(self, **kwargs):
        other = copy(self)
        for key, val in kwargs.items():
            setattr(other, key, val)
        return other

    def filter_video(self, video: Video):
        """Returns true if a video should not be saved to the database."""
        if not self.series_config:
            raise ValueError("Missing required series_config.")
        if not video.published_at:
            return True
        if video.published_at <= self.series_config.get('start', 0):
            return True
        if video.video_id in self.series_config.get('ignore_video_ids', []):
            return True
        if video.tombstone is not None:
            return True
        return False
