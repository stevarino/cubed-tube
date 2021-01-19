
from lib.models import Series, Channel, Video, Misc, Playlist, pw

from collections import defaultdict
from copy import copy
from dataclasses import dataclass, field
import datetime
import json
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




def generate_template_context(config: Dict):
    defaults = [s['slug'] for s in config['series'] if s.get('default')]
    assert len(defaults) == 1, 'Only one series should be marked default'
    default_series = defaults[0]
    series_list = [[s['slug'], s['title']] for s in config['series']]
    context = {
        'title': config['title'],
        'default_series': json.dumps(default_series),
        'series_list': json.dumps(series_list),
        'now': str(int(datetime.datetime.now().timestamp())),
        'version': config['version'],
    }
    context['hermit_counts'] = json.dumps(get_videos_by_hermit())
    for data in Misc.select():
        context[data.key] = data.value
    return context

def get_videos_by_hermit():
    vids = (
        Video.select(
            Video.series, 
            Video.playlist.channel, 
            pw.fn.COUNT(Video.video_id).alias('cnt'))
        .join(Playlist)
        .join(Channel)
        .group_by(Video.series, Video.playlist.channel)
        .order_by(pw.fn.Lower(Video.playlist.channel.tag))
    )
    seasons = set()
    data = defaultdict(dict)
    for v in vids:
        seasons.add(v.series.slug)
        data[v.playlist.channel.tag][v.series.slug] = v.cnt
    seasons = sorted(seasons)
    totals = {}
    for ch in data:
        data[ch] = {s: data[ch].get(s, 0) for s in seasons}
        data[ch]['total'] = sum(data[ch][s] for s in seasons)
    for season in seasons:
        totals[season] = sum(data[ch].get(season, 0) for ch in data.keys())
    totals['total'] = sum(totals.values())
    data['total'] = totals
    for ch in data:
        for season in data[ch]:
            if not data[ch][season]:
                data[ch][season] = ''
    return data
