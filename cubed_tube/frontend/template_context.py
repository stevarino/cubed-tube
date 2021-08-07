"""
General SQL-heavy functions for renderings
"""

from collections import defaultdict
import json
import datetime

from cubed_tube.lib import schema
from cubed_tube.lib.models import Misc, Video, Channel, pw

def generate_context(config: schema.Configuration, creds: schema.Credentials):
    defaults = [s.slug for s in config.series if s.default]
    assert len(defaults) == 1, 'Only one series should be marked default'
    default_series = defaults[0]
    series_list = [[s.slug, s.title] for s in config.series]
    api_domain = (creds.backend and creds.backend.domain) or ''
    context = {
        'title': config.title,
        'window_vars': {
            'series': json.dumps(default_series),
            'all_series': json.dumps(series_list),
            'backend_version': json.dumps(config.version),
            'API_DOMAIN': json.dumps(api_domain)
        },
        'page': {
            'menu_links': generate_link_menus(config),
            'title': config.title,
            'header': config.site.header,
        },
    }

    context['channel_counts'] = json.dumps(get_videos_by_channel())
    for data in Misc.select():
        context[data.key] = data.value
    return context


def generate_link_menus(config: schema.Configuration):
    if not config.site.menu_links:
        return []
    return [link.as_dict() for link in config.site.menu_links]


def get_videos_by_channel():
    vids = (
        Video.select(
            Video.series, 
            Channel.tag.alias('ch_tag'), 
            pw.fn.COUNT(Video.video_id).alias('cnt'))
        .join(Channel, on=(Video.channel == Channel.name), attr='ch')
        .group_by(Video.series, Video.channel)
        .order_by(pw.fn.Lower(Channel.tag))
    ).objects()
    seasons = set()
    data = defaultdict(dict)
    for v in vids:
        seasons.add(v.series.slug)
        data[v.ch_tag][v.series.slug] = v.cnt
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
