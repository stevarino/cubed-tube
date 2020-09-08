"""
Reads from the database and produces html files.
"""

import common
from models import Video, Playlist, Channel, Series

import argparse
from collections import defaultdict
from glob import glob
import itertools
import json
import os
import re
import shutil
from typing import Dict, List
import yaml

def process_html(filename: str, context: Dict[str, str]):
    """Poor man's html-includes, because I miss php apparently."""
    with open(filename, 'r') as fp:
        html = fp.read()
    parts = re.split(r'(<%.+%>)', html)
    for i, part in enumerate(parts):
        if not part.startswith('<%'):
            continue
        tag_type, data = re.match(r'<%\s*(\w+)\s*(.*?)\s*%>', part).groups()
        if tag_type == 'include':
            assert '..' not in data, "lazy path escaping"
            parts[i] = process_html('templates/'+ data, context)
        elif tag_type == 'print':
            assert data in context, f"Missing context {data} - {filename}"
            parts[i] = context[data]
        else:
            raise ValueError(f"Unrecognized tag_type: {tag_type}")
    return ''.join(parts)

def render_html(default_series: str, series_list: List[Dict[str, str]]):
    context = {
        'default_series': json.dumps(default_series),
        'series_list': json.dumps(series_list)
    }
    for html_file in glob('templates/**/*.html', recursive=True):
        out_file = "output" + html_file[9:]
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, 'w') as fp:
            fp.write(process_html(html_file, context))

def check_order(videos: List[Dict], attempt=0):
    """
    Validates that videos are sorted by position and attempts to fix any errors
    found by reordering by video published time and playlist added time (see
    giant note below...).
    """
    vids_by_ch = defaultdict(list)
    for video in videos:
        vids_by_ch[video['ch_name']].append(video)
    
    for ch, vids in vids_by_ch.items():
        prev = {}
        for i, vid in enumerate(vids):
            if vid['position'] is None:
                continue
            # position is absolutely trustable, but has no meaning when joined
            # across playlists/channels. Video publish timestamp (aliased as
            # timestamp by default) is usually trustworthy, except when someone
            # adds a several year-old Bieber video (or a video is republished).
            # In this case, we use playlist added date, but that's less
            # overall reliable. So far there have been no videos where both 
            # times are inaccurate. If this does happen, maybe we can take the
            # average of surrounding videos (assuming we an identify the
            # problem video)
            if prev and prev['position'] > vid['position']:
                if prev['timestamp'] > vid['playlist_at']:
                    vid['timestamp'] = vid['playlist_at']
                elif prev['playlist_at'] > vid['timestamp']:
                    prev['timestamp'] = prev['playlist_at']
                elif attempt:
                    print(
                        f"  WARNINNG: {ch} {prev['position']} < "
                        f"{vid['position']}")
            prev = vid

    vids = sorted(
        itertools.chain(*vids_by_ch.values()),
        key=lambda k: k['timestamp'])

    if not attempt:
        print('... trying again.')
        return check_order(vids, 1)
    return vids


def render_series(series: Dict):
    videos = (Video.select()
        .join(Playlist)
        .join(Channel)
        .join_from(Video, Series)
        .where(Video.series.slug == series['slug'])
        .order_by(Video.published_at)
    )
    data = {'channels': {}, 'videos': []}

    for video in videos:
        if video.title is None:
            continue
        data['videos'].append({
            'video_id': video.video_id,
            'timestamp': video.published_at,
            'published_at': video.published_at,
            'playlist_at': video.playlist_at,
            'position': video.position,
            'desc': video.description,
            'title': video.title,
            'ch_name': video.playlist.channel.name,
        })
        if video.playlist.channel.name not in data['channels']: 
            thumb = {}
            if video.playlist.channel.thumbnails:
                thumbs = json.loads(video.playlist.channel.thumbnails)
                thumb = thumbs['default']['url']
            data['channels'][video.playlist.channel.name] = {
                'ch_id': video.playlist.channel.channel_id,
                'ch_title': video.playlist.channel.tag,
                'ch_custom_url': video.playlist.channel.custom_url,
                'ch_thumbs': thumb,
            }

    data['videos'] = check_order(data['videos'])
    
    for vid in data['videos']:
        for key in 'published_at playlist_at position'.split():
            del vid[key]

    with open(f'output/data/{series["slug"]}.json', 'w') as fp:
        fp.write(json.dumps(data))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--series', '-s', nargs='*')
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with open('playlists.yaml') as fp:
        config = yaml.safe_load(fp)

    shutil.rmtree('output/')
    os.makedirs('output/data', exist_ok=True)

    for series in config['series']:
        print(f'Processing {series["slug"]}')
        if args.series and series['slug'] not in args.series:
            continue
        render_series(series)

    render_html(
        [s['slug'] for s in config['series'] if s.get('default')][0],
        [[s['slug'], s['title']] for s in config['series']])
    shutil.copytree('templates/static', 'output/static')

if __name__ == "__main__":
    main()