# YouTube Quota Limit = 10k/day
# crontab = */10 (6x/hour, 144/day)
# => 69.4 quota/run (round down to 60)
# playlist updating = ~40 quota/run
# currently 11339 videos in system
# => scan entire library = 227 quota, or 12 runs, or 2 hours

from hermit_tube.lib.common import Context, chunk
from hermit_tube.lib.models import (
    Misc, Series, Channel, Playlist, Video, pw, db, init_database)
from hermit_tube.lib import trends
from hermit_tube.lib.util import root

import argparse
from dataclasses import dataclass
import datetime
import json
import os
import re
import socket
import traceback
from typing import Dict, List
import urllib.request, urllib.parse
import yaml

API_URL = 'https://www.googleapis.com/youtube/v3/'
YT_PLAYLIST = re.compile(r'https://www.youtube.com/playlist\?list=([^&]+)')

# Matches PT15M33S and P1DT2H3M4S as timedelta compatible dicts
ISO8601_DUR = re.compile(
    r'P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?'
    r'(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?')


@dataclass
class YouTubeRequest:
    endpoint: str
    args: Dict
    cost: int = 1
    etag: str = None


def _yt_get(ctx: Context, req: YouTubeRequest):
    req.args['key'] = ctx.api_key
    request = urllib.request.Request(
        f'{API_URL}{req.endpoint}?{urllib.parse.urlencode(req.args)}')
    # NOTE: https://issuetracker.google.com/issues/176760791
    # if req.etag:
    #     request.add_header('if-none-match', f'"{req.etag}"')
    ctx.cost.add(req.cost)
    try:
        for timeout in [5, 10, 20, 40, 80]:
            try:
                resp = urllib.request.urlopen(request, timeout=timeout)
                # print(resp.headers)
                data = json.loads(resp.read().decode(
                    resp.info().get_content_charset('utf-8')))
            except socket.timeout:
                print(f'  timeout {req.endpoint} @ {timeout}')
                continue
            else:
                break
        else:
            raise socket.timeout()
    except Exception:
        print('Exception from:', req.endpoint)
        print(json.dumps(req.args, indent=2))
        raise
    return data

def _yt_get_generator(ctx: Context, response: Dict, req: YouTubeRequest):
    """Yields an item from a response, making additional requests as needed."""
    while True:
        for item in response['items']:
            yield item
        if 'nextPageToken' not in response:
            break
        req.args['pageToken'] = response['nextPageToken']
        response = _yt_get(ctx, req)

def _yt_get_many(ctx: Context, req: YouTubeRequest):
    while True:
        items = _yt_get(ctx, req)
        for item in items['items']:
            yield item
        if 'nextPageToken' not in items:
            break
        req.args['pageToken'] = items['nextPageToken']

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
            chan.id = Channel.select(pw.fn.MAX(Channel.id)).scalar() + 1
            if 'channel' in channel:
                channel_name = channel['channel']
                channel = _yt_get(ctx, YouTubeRequest(
                    endpoint='channels', args={'forUsername': channel_name}))
                if 'items' not in channel:
                    raise ValueError("Unable to find channel " + channel_name)
                channel_id = channel['items'][0]['id']
            elif YT_PLAYLIST.match(channel.get('playlist', '')):
                playlist_id = YT_PLAYLIST.match(channel['playlist'])[1]
                args =  {'playlistId': playlist_id, 'part': 'id,snippet'}
                playlist = _yt_get(ctx, YouTubeRequest(
                    endpoint='playlistItems', args=args))
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
    chans = (
        Channel.select(
            Channel,
            Channel.channel_id.in_(chan_ids).alias('targeted')
        )
        .where(
            Channel.last_scanned.is_null() | 
            (Channel.last_scanned <= (ctx.now - 24*3600)))
        .order_by(pw.SQL('targeted').desc())
        .limit(50))
    
    chan_map = {c.channel_id: c for c in chans if c.channel_id}

    if not chan_map:
        return
    chan_args = dict(
        id=','.join(c.channel_id for c in chan_map.values()),
        part='snippet,statistics',
        maxResults=50)
    items = _yt_get(ctx, YouTubeRequest(
        endpoint='channels', args=chan_args))['items']
    for item in items:
        chan = chan_map[item['id']]
        chan.last_scanned = ctx.now

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
    

def process_yt_playlist(ctx: Context, ch_name: str, p_id: str):
    args = {
        'playlistId': p_id, 
        'maxResults': 50,
        'part':  'snippet,contentDetails'
    }
    play, _ = Playlist.get_or_create(
        playlist_id=p_id, playlist_type='youtube_pl', channel=ctx.channel)
    req = YouTubeRequest('playlistItems', args, etag=play.etag)
    try:
        videos = _yt_get(ctx, req)
    except Exception as e:
        print(e)
        return
    play.etag = videos['etag']
    play.save()
    for i, result in enumerate(_yt_get_generator(ctx, videos, req)):
        update_video(ctx, result['snippet']['resourceId']['videoId'], result,
                     defaults={'playlist': play, 'series': ctx.series, 
                               'channel': get_yt_channel_id(ch_name)})
    print(f'    Playlist ID {p_id} ({i+1})')


def _parse_ts(dt_str):
    dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    return int(dt.timestamp())


def update_video(ctx: Context, video_id: str, result: Dict,
                 filter_vid: bool = True, defaults: Dict = None):
    """Write a video to the database"""
    vid, _ = Video.get_or_create(
            video_type='youtube', 
            video_id=video_id,
            defaults=defaults)
    vid.title = result['snippet']['title']
    vid.description = result['snippet']['description']
    vid.thumbnails = json.dumps(result['snippet']['thumbnails'])

    if 'position' in result['snippet']:
        # playlist fields
        vid.position = result['snippet']['position']
        vid.playlist_at = _parse_ts(result['snippet']['publishedAt'])
        pub_at = result['contentDetails'].get('videoPublishedAt')
        if not pub_at:  # unpublished video, bail out
            return
        vid.published_at = _parse_ts(pub_at)

    if 'duration' in result['contentDetails']:
        # video query fields
        vid.captions = result['contentDetails']['caption']
        match = ISO8601_DUR.match(result['contentDetails']['duration'])
        if match is not None:
            # expired livestreams such as uGW9jJT__IY have value 'P0D'
            vid.length = datetime.timedelta(
                **{k: int(v) if v else 0 for k, v in match.groupdict().items()}
            ).total_seconds()
        vid.last_scanned = ctx.now

        # directly queried videos have the publishedAt 
        pub_at = result['snippet'].get('publishedAt')
        if not pub_at:  # unpublished video, bail out
            return
        vid.published_at = _parse_ts(pub_at)

    if 'statistics' in result:
        _map = {
            'views': 'viewCount',
            'likes': 'likeCount',
            'dislikes': 'dislikeCount',
            'favorites': 'favoriteCount',
            'comments': 'commentCount',
        }
        for key in _map:
            try:
                trends.add_point(
                    trends.get_video_trend(vid, key),
                    ctx.now,
                    int(result['statistics'].get(_map[key])))
            except (ValueError, TypeError):
                pass
    
    if filter_vid and ctx.filter_video(vid):
        return
    vid.save()


def process_channel(ctx: Context, channel: Dict):
    print('  Processing channel', channel['name'])
    ctx_ = load_yt_channel(ctx, channel)
    if 'playlist' in channel and YT_PLAYLIST.match(channel['playlist']):
        playlist_id = YT_PLAYLIST.match(channel['playlist'])[1]
        print('    Processing playlist', playlist_id)
        process_yt_playlist(ctx_, channel['name'], playlist_id)
    elif 'channel' in channel:
        with db.atomic():
            chan, created = Channel.get_or_create(
                name=get_yt_channel_id(channel['name']),
                channel_type=channel.get('type', 'youtube'),
                defaults={'tag': channel['name']})
            if created:
                chan.id = Channel.select(pw.fn.MAX(Channel.id)).scalar() + 1
                channel_name = channel['channel']
                channel = _yt_get(ctx, YouTubeRequest(
                    endpoint='channels', args={'forUsername': channel_name}))
                if 'items' not in channel:
                    raise ValueError("Unable to find channel " + channel_name)
                channel_id = channel['items'][0]['id']
                chan.channel_id = channel_id
                chan.save()
    else:
        raise ValueError("Cannot parse {}".format(channel))

def process_series(ctx: Context, channels: List[Dict[str,str]]):
    print("Working on series", ctx.series.slug)
    videos = {}
    for channel in channels:
        if ctx.channels and channel['name'] not in ctx.channels:
            continue
        try:
            process_channel(ctx, channel)
        except Exception:
            traceback.print_exc()

        # explicit videos
        ch_id = get_yt_channel_id(channel['name'])
        for video in channel.get('videos', []):
            videos[video] = ch_id

    if not videos:
        return
    query = Video.select(Video.video_id).where(
        Video.video_id.in_(list(videos.keys())))
    db_vids = set(v.video_id for v in query)
    new_vids = list(set(videos.keys()) - db_vids)
    if not new_vids:
        return
    print(f"  Requesting explicit videos: {', '.join(new_vids)}")

    def _get_defaults(vid):
        return {
            'defaults': {
                'series': ctx.series,
                'channel': videos[vid['id']],
            }
        }

    missing_vids = get_video_by_ids(ctx, new_vids, kwargs_func=_get_defaults)
    if missing_vids:
        print(f'  WARNING: Videos not found: {", ".join(missing_vids)}')
    
def get_video_by_ids(ctx: Context, video_ids: list[str], kwargs_func: None):
    expected_video_ids = set(video_ids)
    received_video_ids = set()

    for chunked_ids in chunk(video_ids, len(video_ids), 50):
        chan_args = dict(
            id=','.join(chunked_ids),
            part='statistics,snippet,contentDetails')
        for result in _yt_get(ctx, YouTubeRequest(
                endpoint='videos', args=chan_args))['items']:
            received_video_ids.add(result['id'])
            kwargs = {}
            if kwargs_func:
                kwargs = kwargs_func(result)
            update_video(ctx, result['id'], result, **kwargs)

    return expected_video_ids - received_video_ids


def scan_videos(ctx: Context):
    """Use the remaining quota to update video metadata."""
    if ctx.quota is None or ctx.cost.value >= ctx.quota:
        return
    # Given video (A) (last_scan_dur = 1w, pub_dur = 1mo) and video (B) 
    # (last_scan_dur = 10m, pub_dur = 1d), rescan scoring can be calculated
    # by:
    # 
    #   score = last_scan_dur / (pub_dur ** rate_factor)
    # 
    # Assuming video (A) and video (B) have equal scores, rate_factor can be
    # calculated as follows:
    # 
    #   rate_factor = log(scan_time_a / scan_time_b, pub_time_a / pub_time_b)
    rate_factor = 2.033320232
    
    count = 50 * (ctx.quota - ctx.cost.value)
    all_videos = Video.select(
        Video.video_id,
        ((ctx.now - Video.last_scanned) / pw.fn.power(
            ctx.now - Video.published_at, rate_factor
        )).alias('score'),
        Video.last_scanned,
        Video.published_at
    ).where(
        Video.title.is_null(False) & Video.tombstone.is_null()
    ).order_by(
        Video.last_scanned.is_null(False),
        pw.SQL('score').desc(),
        Video.published_at.desc()
    ).limit(count)

    for i, videos in enumerate(chunk(all_videos, count, 50)):
        expected_video_ids = set(v.video_id for v in videos)
        print(f'  Requesting update {i}:')
        print(f'    Start: {videos[0].video_id} ({videos[0].score}, '
              f'{videos[0].last_scanned}, {videos[0].published_at})')
        print(f'    End:   {videos[-1].video_id} ({videos[-1].score}, '
              f'{videos[-1].last_scanned}, {videos[-1].published_at})')

        missing_videos = get_video_by_ids(
            ctx, list(expected_video_ids), 
            kwargs_func=lambda _: {'filter_vid': False})

        if missing_videos:
            print(f'    Tomstoning Videos {", ".join(missing_videos)}')
            Video.update(
                tombstone=ctx.now
            ).where(
                Video.video_id.in_(missing_videos)
            ).execute()


def get_misc(key, default=None):
    rec, _ = Misc.get_or_create(key=key, defaults={'value': default})
    return rec.value

def set_misc(key, val):
    rec, _ = Misc.get_or_create(key=key)
    rec.value = val
    rec.save()

def update_stats(api_cost):
    now = datetime.datetime.now()
    set_misc('last_scan_api', api_cost)
    set_misc('last_scan_time', now.strftime('%Y-%m-%d %H:%M:%S'))

    dailies = json.loads(get_misc('dailies', '{}'))
    ymd = now.strftime('%Y-%m-%d')
    dailies[ymd] = dailies.get(ymd, {'api': 0, 'scans': 0})
    dailies[ymd]['api'] += api_cost
    dailies[ymd]['scans'] += 1
    set_misc('dailies', json.dumps(dailies, sort_keys=True, indent=2))

    latest = (
        Video.select(
            Video, 
            Channel.tag.alias('ch_tag'), 
            Channel.channel_id.alias('ch_id')
        ).join(Channel, on=(Video.channel == Channel.name), attr='ch')
        .order_by(Video.published_at.desc())
        .limit(1)
    ).objects().first()

    set_misc('latest_id', latest.video_id)
    set_misc('latest_dt', latest.published_at)
    set_misc('latest_title', latest.title)
    set_misc('latest_channel_title', latest.ch_tag)
    set_misc('latest_channel_id', latest.ch_id)

def build_argparser(parser):
    parser.add_argument('--series', '-s', nargs='*')
    parser.add_argument('--channel', '-c', nargs='*')
    parser.add_argument('--full', '-f', action='store_true')
    parser.add_argument('--quota', type=int)
    parser.add_argument('--migrate_trends', action='store_true')


def main(args: argparse.Namespace):
    ctx = Context()

    ctx.channels = args.channel
    ctx.quota = args.quota

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with open(root('credentials.yaml')) as fp:
        creds = yaml.safe_load(fp)
    init_database()
    ctx.api_key = creds['api_key']

    with open(root('playlists.yaml')) as fp:
        config = yaml.safe_load(fp)


    try:
        for series in config['series']:
            if args.series and series['slug'] not in args.series:
                continue
            if not args.series and not args.full and not series.get('active', True):
                continue
            series_, _ = Series.get_or_create(
                    slug=series['slug'],
                    defaults={'title': series['title']})
            if series_.title != series['title']:
                series_.title = series['title']
                series_.save()
            c_ctx = ctx.copy(series=series_, series_config=series)
            # process_series(c_ctx, series['channels'])
        scan_videos(ctx)
    finally:
        update_stats(ctx.cost.value)
        print('api cost:', ctx.cost.value)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    build_argparser(parser)
    main(parser.parse_args())
