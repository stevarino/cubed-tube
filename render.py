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
import sys
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
        'series_list': json.dumps(series_list),
        'now': str(int(datetime.datetime.now().timestamp())),
    }
    for html_file in glob('templates/**/*.html', recursive=True):
        out_file = "output" + html_file[9:]
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, 'w') as fp:
            fp.write(process_html(html_file, context))

def check_order(data: Dict, attempt=0):
    """
    Validates that videos are sorted by position and attempts to fix any errors
    found by reordering by video published time and playlist added time (see
    giant note below...).
    """
    videos = data['videos']
    vids_by_ch = defaultdict(list)
    for video in videos:
        vids_by_ch[video['ch']].append(video)
    
    for ch, vids in vids_by_ch.items():
        prev = {}
        for vid in vids:
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
                if prev['ts'] > vid['playlist_at']:
                    vid['ts'] = vid['playlist_at']
                elif prev['playlist_at'] > vid['ts']:
                    prev['ts'] = prev['playlist_at']
                # elif attempt:
                #     print(
                #         f"  WARNINNG: {data['channels'][ch]['name']} "
                #         f"{prev['position']} < {vid['position']}")
            prev = vid

    vids = sorted(
        itertools.chain(*vids_by_ch.values()),
        key=lambda k: k['ts'])

    if not attempt:
        return check_order(data, 1)
    return vids


def render_series(series: Dict):
    videos = (Video.select()
        .join(Playlist)
        .join(Channel)
        .join_from(Video, Series)
        .where(Video.series.slug == series['slug'])
        .order_by(Video.published_at)
    )
    data = {'channels': [], 'videos': []}

    channels = {}
    channel_lookup = {}
    descs = {}
    for video in videos:
        if video.playlist.channel.name not in channels: 
            thumb = {}
            if video.playlist.channel.thumbnails:
                thumbs = json.loads(video.playlist.channel.thumbnails)
                thumb = thumbs['default']['url']
            channels[video.playlist.channel.name] = {
                'id': video.playlist.channel.channel_id,
                'name': video.playlist.channel.name,
                't': video.playlist.channel.tag,
                # 'url': video.playlist.channel.custom_url,
                'thumb': thumb,
                'count': 1,
            }
        else:
            channels[video.playlist.channel.name]['count'] += 1
    channel_names = sorted(
        channels.keys(), key=lambda k: channels[k]['count'], reverse=True)
    for i, name in enumerate(channel_names):
        data['channels'].append(channels[name])
        del data['channels'][i]['count']
        channel_lookup[name] = i

    for video in videos:
        if video.title is None:
            continue
        descs[video.video_id] = video.description
        data['videos'].append({
            'id': video.video_id,
            'ts': video.published_at,
            'published_at': video.published_at,
            'playlist_at': video.playlist_at,
            'position': video.position,
            't': video.title,
            'ch': channel_lookup[video.playlist.channel.name],
        })

    data['videos'] = check_order(data)
    
    for vid in data['videos']:
        for key in 'published_at playlist_at position'.split():
            del vid[key]

    with open(f'output/data/{series["slug"]}.json', 'w') as fp:
        fp.write(json.dumps(data))
    with open(f'output/data/{series["slug"]}.desc.json', 'w') as fp:
        fp.write(json.dumps(descs))

def copytree(src, dst, symlinks=False, ignore=None):
    """https://stackoverflow.com/a/12514470"""
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--series', '-s', nargs='*')
    parser.add_argument('--quick', '-q', action='store_true')
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with open('playlists.yaml') as fp:
        config = yaml.safe_load(fp)

    if not args.quick:
        if os.path.exists('output'):
            shutil.rmtree('output/')
        os.makedirs('output/data', exist_ok=True)
        os.makedirs('output/static', exist_ok=True)

        for series in config['series']:
            print(f'Processing {series["slug"]}')
            if args.series and series['slug'] not in args.series:
                continue
            render_series(series)

    render_html(
        [s['slug'] for s in config['series'] if s.get('default')][0],
        [[s['slug'], s['title']] for s in config['series']])
    copytree('templates/static', 'output/static')

if __name__ == "__main__":
    main()