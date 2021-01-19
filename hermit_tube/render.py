"""
Reads from the database and produces html files.
"""

from hermit_tube.lib.common import Context, generate_template_context
from hermit_tube.lib.models import Video, Playlist, Channel, Series, Misc, init_database

import argparse
from collections import defaultdict
import datetime
from glob import glob
import gzip
import hashlib
import html
import json
import os
import re
import shutil
import sys
from typing import Dict, List, Tuple, Union
import yaml

from jinja2 import Environment, PackageLoader
import peewee as pw

def sha1(value: Union[str, bytes]) -> str:  # pylint: disable=unsubscriptable-object
    """Convenience function to convert a string into a sha1 hex string"""
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha1(value).hexdigest()

def render_static(config: Dict):
    os.makedirs( 'output/static', exist_ok=True)
    env = Environment(loader=PackageLoader(__name__))
    context = generate_template_context(config)
    for html_file in glob('templates/**/*.html', recursive=True):
        if 'wsgi' in html_file:  # auth site
            continue
        html_file = html_file[10:].replace('\\', '/')
        out_file = os.path.join("output", html_file)
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, 'w') as fp:
            fp.write(env.get_template(html_file).render(**context))


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
        # gzip takes into account file metadata when hashing, therefore it is
        # necessary to separate hashing from the logical file to ensure
        # deterministic output and avoid false invalidation of caches.
        #
        # TLDR: gzip.open() bad.
        with open(f'output/data/{slug}/desc/{sig}.json.gz', 'wb') as fp:
            with gzip.GzipFile(
                    fileobj=fp, filename='', mtime=0, mode='wb') as fpz:
                fpz.write(stack_bytes)
        print(f'Hash: {sig} ({len(stack)})')
        stack.clear()
        sigs.append(sig)

    for vid, desc in descs.items():
        stack[vid] = desc
        _write()
    _write(True)
    return sigs


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

def build_argparser(parser: argparse.ArgumentParser):
    parser.add_argument('--series', '-s', nargs='*')
    parser.add_argument('--quick', '-q', action='store_true')

def main(args: argparse.Namespace):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with open('playlists.yaml') as fp:
        config = yaml.safe_load(fp)
    init_database()

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
    parser = argparse.ArgumentParser()
    build_argparser(parser)
    main(parser.parse_args())
