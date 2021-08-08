"""
scraper.py - Imports video data from YouTube

This module is honestly a bit of a mess and should probably be refactored. I
haven't figured out what that would look like yet.

Function map (note that some are called in multiple stacks):

  - main
    - process_series -- Load/Create a series (hc7)
      - process_channel -- Processes a channel (BdoubleO100)
        - load_yt_channel -- Load/Create a channel, either by playlist or channel name
        - process_yt_playlist -- If a channel has a playlist, get its videos
          - update_video -- Write video data
      - get_video_by_ids -- Update any explicitly listed videos (non-playlist)
        - update_video -- YouTube record to database
    - scan_videos -- Update video statistics/metadata regularly, focusing on new videos
      - get_video_by_ids -- Read video data from YouTube
        - update_video -- YouTube record to database


YouTube Quota Math:
    YouTube Quota Limit = 10k/day
    crontab = */10 (6x/hour, 144/day)
    => 69.4 quota/run (round down to 60)
    playlist updating = ~40 quota/run
    currently 11339 videos in system
    => scan entire library = 227 quota, or 12 runs, or 2 hours
"""

import argparse
from dataclasses import dataclass, field
import datetime
import json
import re
import socket
import traceback
import time
from typing import Optional
import urllib.request, urllib.parse

from cubed_tube.lib.common import filter_video
from cubed_tube.lib import trends, schema, models as m
from cubed_tube.lib.util import load_credentials, load_config, chunk

API_URL = 'https://www.googleapis.com/youtube/v3/'
YT_PLAYLIST = re.compile(r'https://www.youtube.com/playlist\?list=([^&]+)')

# Matches PT15M33S and P1DT2H3M4S as timedelta compatible dicts
ISO8601_DUR = re.compile(
    r'P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?'
    r'(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?')


@dataclass
class Context:
    """A dataclass of convenience fields, useful for branching contexts."""
    cost: int = 0
    quota: int = None
    channels: list[str] = field(default_factory=list)
    now: int = field(default_factory=lambda: int(time.time()))


@dataclass
class YouTubeRequest:
    endpoint: str
    args: dict
    cost: int = 1
    etag: str = None


def _yt_get(ctx: Context, req: YouTubeRequest):
    req.args['key'] = load_credentials().scraper.yt_api_key
    request = urllib.request.Request(
        f'{API_URL}{req.endpoint}?{urllib.parse.urlencode(req.args)}')
    # NOTE: https://issuetracker.google.com/issues/176760791
    # if req.etag:
    #     request.add_header('if-none-match', f'"{req.etag}"')
    ctx.cost += req.cost
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

def _yt_get_generator(ctx: Context, response: dict, req: YouTubeRequest):
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

def load_yt_channel(ctx: Context, channel: schema.ConfigChannel
                    ) -> m.Channel:
    """Creates or retrieves a channel record, ensuring it is up to date."""
    with m.DATABASE.atomic():
        chan, created = m.Channel.get_or_create(
            name=get_yt_channel_id(channel.name),
            channel_type=channel.type,
            defaults={'tag': channel.name})
        if created:
            max_id = m.Channel.select(
                m.pw.fn.MAX(m.Channel.id)
            ).scalar() or 0
            chan.id = max_id + 1
            if channel.channel:
                channel_name = channel.channel
                ch_resp = _yt_get(ctx, YouTubeRequest(
                    endpoint='channels', args={'forUsername': channel_name}))
                if 'items' not in ch_resp:
                    raise ValueError("Unable to find channel " + channel_name)
                channel_id = ch_resp['items'][0]['id']
            elif YT_PLAYLIST.match(channel.playlist or ''):
                playlist_id = YT_PLAYLIST.match(channel.playlist)[1]
                args =  {'playlistId': playlist_id, 'part': 'id,snippet'}
                playlist_resp = _yt_get(ctx, YouTubeRequest(
                    endpoint='playlistItems', args=args))
                if 'items' not in playlist_resp:
                    raise ValueError("Unable to find playlist {} ({})".format(
                        playlist_id, channel['name']))
                channel_id = playlist_resp['items'][0]['snippet']['channelId']
            else:
                raise ValueError(f"Unrecognized channel: {channel.as_dict()}")
            chan.channel_id = channel_id
            chan.save()
    update_yt_channel(ctx, [chan.channel_id])
    return chan

def update_yt_channel(ctx: Context, chan_ids: list[str]):
    chans = (
        m.Channel.select(
            m.Channel,
            m.Channel.channel_id.in_(chan_ids).alias('targeted')
        )
        .where(
            m.Channel.last_scanned.is_null() | 
            (m.Channel.last_scanned <= (ctx.now - 24*3600)))
        .order_by(m.pw.SQL('targeted').desc())
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
        chan: m.Channel = chan_map[item['id']]
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
    

def process_yt_playlist(ctx: Context, series: schema.ConfigSeries,
                        channel: schema.ConfigChannel):
    playlist = YT_PLAYLIST.match(channel.playlist)[1]
    play, _ = m.Playlist.get_or_create(
        playlist_id=playlist, playlist_type='youtube_pl',
        channel=channel.record)
    args = {
        'playlistId': playlist, 
        'maxResults': 50,
        'part':  'snippet,contentDetails'
    }
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
                     series=series, defaults={
                         'playlist': play,
                         'series': series.record, 
                         'channel': get_yt_channel_id(channel.name)})
    print(f'    Playlist ID {playlist} ({i+1})')


def _parse_ts(dt_str: str):
    dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    return int(dt.timestamp())


def update_video(ctx: Context, video_id: str, result: dict,
                 defaults: dict = None,
                 series: Optional[schema.ConfigSeries] = None):
    """Write a video to the database"""
    vid, _ = m.Video.get_or_create(
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
    
    if series and filter_video(series, vid):
        return
    vid.save()


def process_channel(ctx: Context, series: schema.ConfigSeries,
                    channel: schema.ConfigChannel):
    print('  Processing channel', channel.name)
    channel.record = load_yt_channel(ctx, channel)
    if channel.playlist and YT_PLAYLIST.match(channel.playlist):
        playlist_id = YT_PLAYLIST.match(channel.playlist)[1]
        print('    Processing playlist', playlist_id)
        process_yt_playlist(ctx, series, channel)

def process_series(ctx: Context, series: schema.ConfigSeries):
    print("Working on series", series.slug)
    videos = {}
    for channel in series.channels:
        # filter for cli specified channels
        if ctx.channels and channel.name not in ctx.channels:
            continue
        try:
            process_channel(ctx, series, channel)
        except Exception:
            traceback.print_exc()

        # explicit videos
        ch_id = get_yt_channel_id(channel.name)
        for video in (channel.videos or []):
            videos[video] = ch_id

    if not videos:
        return
    query = m.Video.select(m.Video.video_id).where(
        m.Video.video_id.in_(list(videos.keys())))
    db_vids = set(v.video_id for v in query)
    new_vids = list(set(videos.keys()) - db_vids)
    if not new_vids:
        return
    print(f"  Requesting explicit videos: {', '.join(new_vids)}")

    def _get_defaults(vid):
        return {
            'defaults': {
                'series': series.record,
                'channel': videos[vid['id']],
            }
        }

    missing_vids = get_video_by_ids(ctx, new_vids, kwargs_func=_get_defaults)
    if missing_vids:
        print(f'  WARNING: Videos not found: {", ".join(missing_vids)}')
    
def get_video_by_ids(ctx: Context, video_ids: list[str], kwargs_func=None):
    expected_video_ids = set(video_ids)
    received_video_ids = set()

    for chunked_ids in chunk(video_ids, len(video_ids), 50):
        with m.DATABASE.atomic():
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
    if ctx.quota is None or ctx.cost >= ctx.quota:
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
    
    count = 50 * (ctx.quota - ctx.cost)
    all_videos: list[m.Video] = m.Video.select(
        m.Video.video_id,
        ((ctx.now - m.Video.last_scanned) / m.pw.fn.power(
            ctx.now - m.Video.published_at, rate_factor
        )).alias('score'),
        m.Video.last_scanned,
        m.Video.published_at
    ).where(
        m.Video.title.is_null(False) & m.Video.tombstone.is_null()
    ).order_by(
        m.Video.last_scanned.is_null(False),
        m.pw.SQL('score').desc(),
        m.Video.published_at.desc()
    ).limit(count)

    for i, videos in enumerate(chunk(all_videos, count, 50)):
        expected_video_ids = set(v.video_id for v in videos)
        print(f'  Requesting update {i}:')
        print(f'    Start: {videos[0].video_id} ({videos[0].score}, '
              f'{videos[0].last_scanned}, {videos[0].published_at})')
        print(f'    End:   {videos[-1].video_id} ({videos[-1].score}, '
              f'{videos[-1].last_scanned}, {videos[-1].published_at})')

        missing_videos = get_video_by_ids(ctx, list(expected_video_ids))

        if missing_videos:
            print(f'    Tomstoning Videos {", ".join(missing_videos)}')
            m.Video.update(
                tombstone=ctx.now
            ).where(
                m.Video.video_id.in_(missing_videos)
            ).execute()


def get_misc(key, default=None) -> m.Misc:
    rec, _ = m.Misc.get_or_create(key=key, defaults={'value': default})
    return rec.value

def set_misc(key, val):
    rec, _ = m.Misc.get_or_create(key=key)
    rec.value = val
    rec.save()

def update_stats(api_cost):
    now = datetime.datetime.now()
    set_misc('last_scan_api', api_cost)
    set_misc('last_scan_time', now.strftime('%Y-%m-%d %H:%M:%S'))

    dailies: dict = json.loads(get_misc('dailies', '{}'))
    dailies = {k: dailies[k] for k in sorted(dailies.keys())[-30:]}
    ymd = now.strftime('%Y-%m-%d')
    dailies[ymd] = dailies.get(ymd, {'api': 0, 'scans': 0})
    dailies[ymd]['api'] += api_cost
    dailies[ymd]['scans'] += 1
    set_misc('dailies', json.dumps(dailies, sort_keys=True, indent=2))

    latest = (
        m.Video.select(
            m.Video, 
            m.Channel.tag.alias('ch_tag'), 
            m.Channel.channel_id.alias('ch_id')
        ).join(
            m.Channel, on=(m.Video.channel == m.Channel.name),
            attr='ch'
        ).order_by(m.Video.published_at.desc())
        .limit(1)
    ).objects().first()

    set_misc('latest_id', latest.video_id)
    set_misc('latest_dt', latest.published_at)
    set_misc('latest_title', latest.title)
    set_misc('latest_channel_title', latest.ch_tag)
    set_misc('latest_channel_id', latest.ch_id)

def build_argparser(parser: argparse.ArgumentParser):
    series_help = ('Specify one ore more series to explicitly scan (default '
                   'is active only)'),
    channel_help = 'Only scan the specified channels (default is all)'
    full_help = 'Scan all series - useful for new databases'
    parser.add_argument('--series', '-s', nargs='*', help=series_help)
    parser.add_argument('--channel', '-c', nargs='*', help=channel_help)
    parser.add_argument('--full', '-f', action='store_true', help=full_help)
    parser.add_argument('--quota', type=int)
    parser.add_argument('--migrate_trends', action='store_true')


def main(args: argparse.Namespace):
    ctx = Context(quota = args.quota, channels = args.channel)

    m.init_database()
    config = load_config()

    try:
        for series in config.series:
            if args.series and series.slug not in args.series:
                continue
            if not args.series and not args.full and not series.active:
                continue
            series.record, _ = m.Series.get_or_create(
                slug=series.slug,
                defaults={'title': series.title})
            if series.record.title != series.title:
                series.record.title = series.title
                series.record.save()
            process_series(ctx, series)
        scan_videos(ctx)
    finally:
        update_stats(ctx.cost)
        print('api cost:', ctx.cost)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    build_argparser(parser)
    main(parser.parse_args())
