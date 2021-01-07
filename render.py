"""
Reads from the database and produces html files.
"""

from common import Context
from models import Video, Playlist, Channel, Series, Misc

import argparse
from collections import defaultdict
import datetime
from glob import glob
import gzip
import hashlib
import html
import json
import os
import peewee as pw
import re
import shutil
import sys
from typing import Dict, List, Tuple, Union
import yaml

def sha1(value: Union[str, bytes]) -> str:  # pylint: disable=unsubscriptable-object
    """Convenience function to convert a string into a sha1 hex string"""
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha1(value).hexdigest()

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
            skip_row_label = False
            if isinstance(table_data, list):
                table_data = {i: row for i, row in enumerate(table_data)}
                skip_row_label = True
            for row in sorted(table_data.keys()):
                for col in table_data[row].keys():
                    if col not in columns:
                        columns.append(col)
            output = ['<table><thead><tr><td></td>']
            [output.append(f'<th>{col}</th>') for col in columns]
            output.append('</tr></thead>')
            for row in table_data.keys():
                table_row = table_data[row]
                output.append(f'<tr>')
                if not skip_row_label:
                    output.append(f'<th>{row}</th>')
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
        'version': config['version'],
    }
    context['hermit_counts'] = json.dumps(get_videos_by_hermit())
    for data in Misc.select():
        context[data.key] = data.value
    for html_file in glob('templates/**/*.html', recursive=True):
        out_file = "output" + html_file[9:]
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, 'w') as fp:
            fp.write(process_html(html_file, context))

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


def render_series(context: Context):
    slug = context.series_config['slug']
    videos = (Video.select()
        .join(Playlist)
        .join(Channel)
        .join_from(Video, Series)
        .where(Video.series.slug == slug)
        .order_by(Video.published_at)
    )
    data = {'channels': [], 'videos': []}

    channels = {}
    channel_lookup = {}
    descs = {}
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
        else:
            channels[ch_name]['count'] += 1
    channel_names = sorted(
        channels.keys(), key=lambda k: channels[k]['count'], reverse=True)
    for i, name in enumerate(channel_names):
        data['channels'].append(channels[name])
        del data['channels'][i]['count']
        channel_lookup[name] = i

    for video in videos:
        if context.filter_video(video):
            continue
        descs[video.video_id] = video.description
        data['videos'].append({
            'id': video.video_id,
            'ts': video.published_at,
            't': video.title,
            'ch': channel_lookup[video.playlist.channel.name],
        })
    data['descriptions'] = render_descriptions_by_hash(slug, descs)
    with open(f'output/data/{slug}/index.json', 'w') as fp:
        fp.write(json.dumps(data))
    render_updates(context)

def render_descriptions_by_hash(slug: str, descs: Dict[str, str]):
    os.makedirs(f'output/data/{slug}/desc', exist_ok=True)
    stack = {}
    sigs = []

    def _write(final=False):
        if not stack:
            return
        stack_bytes = json.dumps(stack).encode('utf-8')
        if len(stack_bytes) < 500 * 1024 and not final:
            return
        sig = sha1(stack_bytes)
        # with open(f'output/data/{slug}/desc/{sig}.json', 'w') as fp:
        #     fp.write(json.dumps(stack))
        with gzip.open(f'output/data/{slug}/desc/{sig}.json.gz', 'wb') as fp:
            fp.write(stack_bytes)
        print(f'Hash: {sig} ({len(stack)})')
        stack.clear()
        sigs.append(sig)

    for vid, desc in descs.items():
        stack[vid] = desc
        _write()
    _write(True)
    return sigs
        
# def render_descriptions(slug: str, descs: Dict[str, str]):
#     """Writes out chunks of descriptions."""
#     stack = {}
#     i = 0
#     os.makedirs(f'output/data/{slug}/desc', exist_ok=True)
#     def _write(done: bool):
#         with open(f'output/data/{slug}/desc/{i}.json', 'w') as fp:
#             fp.write(json.dumps({
#                 'videos': stack,
#                 'done': int(done)
#             }))
#     for j, (vid, desc) in enumerate(descs.items()):
#         stack[vid] = desc
#         # TODO: a better approach is a max file size, but how big?
#         if len(stack) < 100:
#             continue
#         _write(j == len(descs) - 1)
#         stack = {}
#         i += 1
#     if stack:
#         _write(True)
#     return render_descriptions_by_hash(slug, descs)


def render_updates(context: Context):
    """Renders json files for the last 10 videos published."""
    slug = context.series_config['slug']
    os.makedirs(f'output/data/{slug}/updates', exist_ok=True)
    vid_hash, vid_id = render_updates_for_series(context)
    with open(f'output/data/{slug}/updates.json', 'w') as f:
        f.write(json.dumps({
            'id': vid_id,
            'hash': vid_hash,
            'version': context.config['version'],
            'promos': [] # TODO....
        }))

def render_updates_for_series(context: Context) -> Tuple[str, str]:
    """Generates the hashed update files, returning the last one."""
    slug = context.series_config['slug']
    prev_hash = None
    prev_id = None
    videos = (Video.select()
        .join(Playlist)
        .join(Channel)
        .join_from(Video, Series)
        .where(Video.series.slug == slug)
        .order_by(Video.published_at.desc())
    )
    videos = [v for v in videos if not context.filter_video(v)]
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
        vid_hash = sha1(f'{slug}/{vid.video_id}')
        with open(f'output/data/{slug}/updates/{vid_hash}.json', 'w') as f:
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

def clear_directory(dir_name):
    """Deletes files/subdirectories in a given directory."""
    # https://stackoverflow.com/a/185941
    if os.path.exists(dir_name):
        for file_name in os.listdir(dir_name):
            file_path = os.path.join(dir_name, file_name)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--series', '-s', nargs='*')
    parser.add_argument('--quick', '-q', action='store_true')
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with open('playlists.yaml') as fp:
        config = yaml.safe_load(fp)

    if args.quick:
        for series in config['series']:
            context = Context(config=config, series_config=series)
            render_updates(context)
    else:
        clear_directory('output')

        for series in config['series']:
            print(f'Processing {series["slug"]}')
            if args.series and series['slug'] not in args.series:
                continue
            render_series(Context(config=config, series_config=series))

    render_static(config)
    copytree('templates/static', 'output/static')

if __name__ == "__main__":
    main()