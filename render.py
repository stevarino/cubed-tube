"""
Reads from the database and produces html files.
"""

import common
from models import Video, Playlist, Channel, Series, Misc

import argparse
from collections import defaultdict
import datetime
from glob import glob
import hashlib
import html
import itertools
import json
import os
import re
import shutil
import sys
from typing import Dict, List, Tuple
import yaml

def sha1(value: str) -> str:
    """Convenience function to convert a string into a sha1 hex string"""
    return hashlib.sha1(value.encode('utf-8')).hexdigest()

def process_html(filename: str, context: Dict[str, str]):
    """Poor man's html-includes, because I miss php apparently."""
    with open(filename, 'r') as fp:
        contents = fp.read()
    parts = re.split(r'(<%.+?%>)', contents)
    for i, part in enumerate(parts):
        if not part.startswith('<%'):
            continue
        tag_parts = re.match(r'<%(=?)\s*(\w+)(\s*)(.*?)\s*%>', part).groups()
        if tag_parts[0] == '=':
            # <%= foo %> convenience syntax for printing
            tag_type, data = ('print', ''.join(tag_parts[1:]).strip())
        else:
            tag_type, data = (tag_parts[1], tag_parts[3])

        if tag_type == 'include':
            assert '..' not in data, "lazy path escaping"
            parts[i] = process_html('templates/'+ data, context)
        elif tag_type == 'print':
            assert data in context, f"Missing context {data} - {filename}"
            parts[i] = context[data]
        elif tag_type == 'pprint':
            assert data in context, f"Missing context {data} - {filename}"
            parts[i] = html.escape(context[data])
            for old, new in [('\n', '<br />'), ('  ', ' &nbsp;')]:
                parts[i] = parts[i].replace(old, new)
        elif tag_type == 'table':
            assert data in context, f"Missing context {data} - {filename}"
            table_data = json.loads(context[data])
            columns = []
            for row in sorted(table_data.keys()):
                for col in table_data[row].keys():
                    if col not in columns:
                        columns.append(col)
            output = ['<table><thead><tr><td></td>']
            [output.append(f'<th>{col}</th>') for col in columns]
            output.append('</tr></thead>')
            for row in sorted(table_data.keys()):
                table_row = table_data[row]
                output.append(f'<tr><th>{row}</th>')
                cols = '</td><td>'.join([
                    str(table_row.get(c, '')) for c in columns])
                output.append(f'<td>{cols}</td></tr>')
            output.append('</table>')
            parts[i] = ''.join(output)
        else:
            raise ValueError(f"Unrecognized tag_type: {tag_type}")
    return ''.join(parts)

def render_static(config: Dict):
    os.makedirs( 'output/static', exist_ok=True)
    defaults = [s['slug'] for s in config['series'] if s.get('default')]
    assert len(defaults) == 1, 'Only one series should be marked default'
    default_series = defaults[0]
    series_list = [[s['slug'], s['title']] for s in config['series']]
    context = {
        'title': config['title'],
        'default_series': json.dumps(default_series),
        'series_list': json.dumps(series_list),
        'now': str(int(datetime.datetime.now().timestamp())),
    }
    for data in Misc.select():
        context[data.key] = data.value
    for html_file in glob('templates/**/*.html', recursive=True):
        out_file = "output" + html_file[9:]
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, 'w') as fp:
            fp.write(process_html(html_file, context))

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
    overrides = {}
    for video in videos:
        ch_name = video.playlist.channel.name
        if ch_name not in channels:
            thumb = {}
            if video.playlist.channel.thumbnails:
                thumbs = json.loads(video.playlist.channel.thumbnails)
                thumb = thumbs['default']['url']
            channels[ch_name] = {
                'id': video.playlist.channel.channel_id,
                'name': ch_name,
                't': video.playlist.channel.tag,
                'thumb': thumb,
                'count': 1,
            }
            for channel in series['channels']:
                if channel['name'] == video.playlist.channel.tag:
                    overrides[ch_name] = channel.get('overrides', {})
        else:
            channels[ch_name]['count'] += 1
    channel_names = sorted(
        channels.keys(), key=lambda k: channels[k]['count'], reverse=True)
    for i, name in enumerate(channel_names):
        data['channels'].append(channels[name])
        del data['channels'][i]['count']
        channel_lookup[name] = i

    for video in videos:
        if video.video_id in overrides.get(video.playlist.channel.name, {}):
            override = overrides[video.playlist.channel.name][video.video_id]
            if override == 0:
                continue
            else:
                video.published_at = override
        if video.title is None:
            continue
        descs[video.video_id] = video.description
        data['videos'].append({
            'id': video.video_id,
            'ts': video.published_at,
            't': video.title,
            'ch': channel_lookup[video.playlist.channel.name],
        })
    os.makedirs(f'output/data/{series["slug"]}/desc', exist_ok=True)
    with open(f'output/data/{series["slug"]}/index.json', 'w') as fp:
        fp.write(json.dumps(data))
    render_descriptions(series["slug"], descs)

        
def render_descriptions(slug: str, descs: Dict[str, str]):
    """Writes out chunks of descriptions."""
    stack = {}
    i = 0
    def _write(done: bool):
        with open(f'output/data/{slug}/desc/{i}.json', 'w') as fp:
            fp.write(json.dumps({
                'videos': stack,
                'done': int(done)
            }))
    for j, (vid, desc) in enumerate(descs.items()):
        stack[vid] = desc
        # TODO: a better approach is a max file size, but how big?
        if len(stack) < 100:
            continue
        _write(j == len(descs) - 1)
        stack = {}
        i += 1
    if stack:
        _write(True)


def render_updates(all_series: List[str]):
    """Renders json files for the last 10 videos published."""
    for series in all_series:
        os.makedirs(f'output/data/{series}/updates', exist_ok=True)
        vid_hash, vid_id = render_updates_for_series(series)
        with open(f'output/data/{series}/updates.json', 'w') as f:
            f.write(json.dumps({
                'id': vid_id,
                'hash': vid_hash,
                'promos': [] # TODO....
            }))

def render_updates_for_series(series: str) -> Tuple[str, str]:
    """Generates the hashed update files, returning the last one."""
    prev_hash = None
    prev_id = None
    videos = (Video.select()
        .join(Playlist)
        .join(Channel)
        .join_from(Video, Series)
        .where(Video.series.slug == series)
        .order_by(Video.published_at.desc())
    )
    for vid in reversed(videos[0:30]):
        vid_data = {
            'id': vid.video_id,
            'ts': vid.published_at,
            't': vid.title,
            'chn': vid.playlist.channel.name,
            'd': vid.description,
            'next': {
                'hash': prev_hash,
                'id': prev_id,
            },
        }
        vid_hash = sha1(f'{series}/{vid.video_id}')
        with open(f'output/data/{series}/updates/{vid_hash}.json', 'w') as f:
            f.write(json.dumps(vid_data))
        prev_hash = vid_hash
        prev_id = vid.video_id
    return vid_hash, vid.video_id

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

        for series in config['series']:
            print(f'Processing {series["slug"]}')
            if args.series and series['slug'] not in args.series:
                continue
            render_series(series)

    render_static(config)
    render_updates([s['slug'] for s in config['series']])
    copytree('templates/static', 'output/static')

if __name__ == "__main__":
    main()