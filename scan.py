

from common import Context
from models import Series, Channel, Playlist, Video, pw, db

import argparse
import datetime
import json
import os
import re
import socket
import time
import traceback
from typing import Dict, List
import urllib.request, urllib.parse
import yaml

API_URL = 'https://www.googleapis.com/youtube/v3/'
YT_PLAYLIST = re.compile(r'https://www.youtube.com/playlist\?list=([^&]+)')

def _yt_get(ctx: Context, endpoint: str, args: Dict, cost=1):
    args['key'] = ctx.api_key
    url = ''.join([API_URL, endpoint, '?', urllib.parse.urlencode(args)])
    ctx.cost.add(cost)
    # print(url)
    try:
        for timeout in [5, 10, 20, 40, 80]:
            try:
                resp = urllib.request.urlopen(url, timeout=timeout)
                data = json.loads(resp.read().decode(
                    resp.info().get_content_charset('utf-8')))
            except socket.timeout:
                print(f'  timeout {endpoint} @ {timeout}')
                continue
            else:
                break
        else:
            raise socket.timeout()
    except Exception:
        print('Exception from:', endpoint)
        print(json.dumps(args, indent=2))
        raise
    return data

def _yt_get_many(ctx: Context, endpoint: str, args: Dict, cost=1):
    while True:
        items = _yt_get(ctx, endpoint, args, cost=cost)
        for item in items['items']:
            yield item
        if 'nextPageToken' not in items:
            break
        args['pageToken'] = items['nextPageToken']

def get_yt_channel_id(channel_name: str):
    """Normalize a channel name into an id."""
    return channel_name.lower().replace(' ', '')

def load_yt_channel(ctx: Context, channel: Dict):
    """Creates or retrieves a channel record, ensuring it is up to date."""
    with db.atomic():
        chan, created = Channel.get_or_create(
            name=get_yt_channel_id(channel['name']),
            channel_type=channel.get('type', 'youtube'),
            defaults={'tag': channel['name']})
        if created:
            if 'channel' in channel:
                channel_name = channel['channel']
                channel = _yt_get(ctx, 'channels', {'forUsername': channel_name})
                if 'items' not in channel:
                    raise ValueError("Unable to find channel " + channel_name)
                channel_id = channel['items'][0]['id']
            elif YT_PLAYLIST.match(channel.get('playlist', '')):
                playlist_id = YT_PLAYLIST.match(channel['playlist'])[1]
                args =  {'playlistId': playlist_id, 'part': 'id,snippet'}
                playlist = _yt_get(ctx, 'playlistItems', args)
                if 'items' not in playlist:
                    raise ValueError("Unable to find playlist {} ({})".format(
                        playlist_id, channel['name']))
                channel_id = playlist['items'][0]['snippet']['channelId']
            else:
                raise ValueError(f"Unrecognized channel: {channel}")
            chan.channel_id = channel_id
            chan.save()

    update_yt_channel(ctx, [chan.channel_id])
    return ctx.copy(channel=chan)

def update_yt_channel(ctx: Context, chan_ids: List[str]):
    now = int(time.time())
    chans = (
        Channel.select(
            Channel,
            Channel.channel_id.in_(chan_ids).alias('targeted')
        )
        .where(
            Channel.last_scanned.is_null() | 
            (Channel.last_scanned <= (now - 24*3600)))
        .order_by(pw.SQL('targeted').desc())
        .limit(50))
    
    chan_map = {c.channel_id: c for c in chans if c.channel_id}

    if not chan_map:
        return
    chan_args = dict(
        id=','.join(c.channel_id for c in chan_map.values()),
        part='snippet,statistics',
        maxResults=50)
    items = _yt_get(ctx, 'channels', chan_args)['items']
    for item in items:
        chan = chan_map[item['id']]
        chan.last_scanned = now

        chan.title = item['snippet']['title']
        chan.custom_url = item['snippet'].get('customUrl')
        chan.description = item['snippet']['description']
        chan.thumbnails = json.dumps(item['snippet']['thumbnails'])
        chan.subscriber_count = item['statistics'].get('subscriberCount')
        chan.video_count = item['statistics'].get('videoCount')
        chan.view_count = item['statistics'].get('viewCount')
        chan.save()

    ''' DOESN'T WORK :-(
    cnt = Channel.bulk_update(list(chan_map.values()), fields=[
        Channel.title, Channel.custom_url, Channel.description,
        Channel.thumbnails, Channel.last_scanned, Channel.subscriber_count,
        Channel.video_count, Channel.view_count])
    print(f"Updated {cnt} rows from {len(chan_map)}")
    '''
    return ctx.copy(channel=chan)
    

def process_yt_playlist(ctx: Context, p_id: str):
    def _parse_ts(dt_str):
        dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return int(dt.timestamp())

    args = {
        'playlistId': p_id, 
        'maxResults': 50,
        'part':  'snippet,contentDetails'
    }
    play, _ = Playlist.get_or_create(
        playlist_id=p_id, playlist_type='youtube_pl', channel=ctx.channel)
    for i, video in enumerate(_yt_get_many(ctx, 'playlistItems', args)):
        vid, _ = Video.get_or_create(
            video_type='youtube', 
            video_id=video['snippet']['resourceId']['videoId'],
            defaults={'playlist': play, 'series': ctx.series})
        vid.title = video['snippet']['title']
        pub_at = video['contentDetails'].get('videoPublishedAt')
        if not pub_at:
            continue
        vid.published_at = _parse_ts(pub_at)
        vid.playlist_at = _parse_ts(video['snippet']['publishedAt'])
        vid.position = video['snippet']['position']
        vid.description = video['snippet']['description']
        vid.thumbnails = json.dumps(video['snippet']['thumbnails'])
        vid.save()
    print(f'    Playlist ID {p_id} ({i+1})')


def process_channel(ctx: Context, channel: Dict):
    print('  Processing channel', channel['name'])
    ctx_ = load_yt_channel(ctx, channel)
    if 'playlist' in channel and YT_PLAYLIST.match(channel['playlist']):
        playlist_id = YT_PLAYLIST.match(channel['playlist'])[1]
        print('    Processing playlist', playlist_id)
        process_yt_playlist(ctx_, playlist_id)
    else:
        raise ValueError("Cannot parse {}".format(channel))

def process_series(ctx: Context, channels: List[Dict[str,str]]):
    print("Working on series", ctx.series.slug)
    for channel in channels:
        if ctx.channels and channel['name'] not in ctx.channels:
            continue
        try:
            process_channel(ctx, channel)
        except Exception:
            traceback.print_exc()

def main():
    ctx = Context()

    parser = argparse.ArgumentParser()
    parser.add_argument('--series', '-s', nargs='*')
    parser.add_argument('--channel', '-c', nargs='*')
    args = parser.parse_args()

    ctx.channels = args.channel

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with open('credentials.yaml') as fp:
        creds = yaml.safe_load(fp)
    ctx.api_key = creds['api_key']

    with open('playlists.yaml') as fp:
        config = yaml.safe_load(fp)

    try:
        for series in config['series']:
            if args.series and series['slug'] not in args.series:
                continue
            if not args.series and not series.get('active', True):
                continue
            series_, _ = Series.get_or_create(
                    slug=series['slug'],
                    defaults={'title': series['title']})
            if series_.title != series['title']:
                series_.title = series['title']
                series_.save()
            c_ctx = ctx.copy(series=series_)
            process_series(c_ctx, series['channels'])
    finally:
        print('api cost:', ctx.cost.value)

if __name__ == "__main__":
    main()