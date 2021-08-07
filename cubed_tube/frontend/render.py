"""
Reads from the database and produces html/js files.
"""

from cubed_tube.lib.common import filter_video
from cubed_tube.lib.models import Video, Channel, Series, init_database
from cubed_tube.lib import schema
from cubed_tube.lib.util import sha1, load_config, load_credentials
from cubed_tube.frontend import template_context

import argparse
from glob import glob
import gzip
import json
import os
import re
import shutil
from typing import Dict, Tuple

from jinja2 import Environment, PackageLoader

TEMPLATE_DIR = 'frontend/templates/'

def render_static(config: schema.Configuration, creds: schema.Credentials):
    os.makedirs('./output/static', exist_ok=True)
    env = Environment(loader=PackageLoader('cubed_tube.frontend'))
    context = template_context.generate_context(config, creds)
    
    out_file = os.path.join("output", 'index.html')
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    print(f'writing {out_file}')
    with open(out_file, 'w') as pf_in:
        pf_in.write(env.get_template('index.html').render(**context))

    if os.path.exists('./content'):
        for html_file in glob(f'./content/**/*.html', recursive=True):
            html_file = html_file.replace('\\', '/')
            html_file_stub = html_file.split('content/', 1)[1]
            dirs = re.sub('\.[a-z]+', '', html_file_stub).split('/')
            dirs.append('index.html')
            out_file = os.path.join('output', *dirs)
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            print(f'writing {out_file}')
            with open(out_file, 'w') as fp_out:
                with open(html_file, 'r') as pf_in:
                    fp_out.write(
                        env.from_string(pf_in.read()).render(**context))


    # join javascript files together
    re_global_var = re.compile(r'^(?:function|var|const) (\w+)', re.MULTILINE)
    global_namespace = {}
    with open(os.path.join("output", 'script.js'), 'w') as pf_in:
        for js_file in glob(f'{TEMPLATE_DIR}scripts/*.js'):
            filename = js_file.replace('\\', '/').split(TEMPLATE_DIR)[-1]
            pf_in.write(f'/*\n * {filename}\n */\n\n')
            with open(js_file, 'r') as js_contents:
                content = js_contents.read()
            for match in re_global_var.findall(content):
                if match in global_namespace:
                    raise ValueError(
                        f'{match} found in {global_namespace[match]} '
                        f'and {filename}')
                global_namespace[match] = filename
            pf_in.write(content)
            pf_in.write('\n\n')

def render_series(config: schema.Configuration, series: schema.ConfigSeries):
    videos: list[Video] = (
        Video.select(Video, Channel, Series)
        .join(Channel, on=(Video.channel == Channel.name), attr='ch')
        .join_from(Video, Series)
        .where(Video.series.slug == series.slug)
        .order_by(Video.published_at)
    )
    data = {'series': series.slug, 'channels': {}, 'videos': []}

    channels = {}
    descs = {}
    for video in videos:
        ch: Channel = video.ch
        if filter_video(series, video):
            continue
        descs[video.video_id] = video.description
        data['videos'].append({
            'id': video.video_id,
            'ts': video.published_at,
            't': video.title,
            'ch': ch.id,
        })
        if ch.id in channels:
            continue
        thumb = {}
        if ch.thumbnails:
            thumbs = json.loads(ch.thumbnails)
            thumb = thumbs['default']['url']
        channels[ch.id] = {
            'id': ch.channel_id,
            'name': ch.name,
            't': ch.tag,
            'thumb': thumb,
        }

    data['channels'] = {
        str(cid): channels[cid] for cid in sorted(channels.keys())
    }

    data['descriptions'] = render_descriptions_by_hash(series.slug, descs)
    with open(f'output/data/{series.slug}/{series.slug}.json', 'w') as fp:
        fp.write(json.dumps(data))
    render_updates(config, series)

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
        print(f'  Hash: {sig} ({len(stack)})')
        stack.clear()
        sigs.append(sig)

    for vid, desc in descs.items():
        stack[vid] = desc
        _write()
    _write(True)
    return sigs


def render_updates(config: schema.Configuration, series: schema.ConfigSeries):
    """Renders json files for the last 10 videos published."""
    os.makedirs(f'output/data/{series.slug}/updates', exist_ok=True)
    vid_hash, vid_id = render_updates_for_series(series)
    with open(f'output/data/{series.slug}/updates.json', 'w') as f:
        f.write(json.dumps({
            'id': vid_id,
            'hash': vid_hash,
            'version': config.version,
            'promos': [] # TODO....
        }))

def render_updates_for_series(series: schema.ConfigSeries) -> Tuple[str, str]:
    """Generates the hashed update files, returning the last one."""
    prev_hash = None
    prev_id = None

    videos: list[Video] = (
        Video.select()
        .join_from(Video, Series)
        .where(Video.series.slug == series.slug)
        .order_by(Video.published_at.desc())
        .limit(30)
    )
    videos = [v for v in videos if not filter_video(series, v)]
    for vid in reversed(videos):
        vid_data = {
            'id': vid.video_id,
            'ts': vid.published_at,
            't': vid.title,
            'chn': vid.channel,  # video.channel = channel.name
            'd': vid.description,
            'next': {
                'hash': prev_hash,
                'id': prev_id,
            },
        }
        vid_hash = sha1(f'{series.slug}/{vid.video_id}')
        filename = f'output/data/{series.slug}/updates/{vid_hash}.json'
        with open(filename, 'w') as f:
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
    config = load_config()
    creds = load_credentials()
    init_database()

    if args.quick:
        for series in config.series:
            render_updates(config, series)
    else:
        clear_directory('output')

        for series in config.series:
            print(f'Processing {series.slug}')
            if args.series and series.slug not in args.series:
                continue
            render_series(config, series)

    render_static(config, creds)
    copytree('frontend/templates/static', 'output/static')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    build_argparser(parser)
    main(parser.parse_args())
