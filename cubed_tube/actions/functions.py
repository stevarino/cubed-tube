
from datetime import datetime
import html
import json
import re
import time
from typing import Dict, cast, List

from cubed_tube.backend import memcached_client as cache
from cubed_tube.lib import util, schemas

MEMCACHE_ENABLED = '$.backend.memcache.enabled'


def disable_memcached(**kwargs):
    overrides = util.load_overrides()
    overrides.credentials[MEMCACHE_ENABLED] = False
    util.save_overrides(overrides)


def enable_memcached(**kwargs):
    overrides = util.load_overrides()
    if MEMCACHE_ENABLED in overrides.credentials:
        del overrides.credentials[MEMCACHE_ENABLED]
    util.save_overrides(overrides)


def flush_user_state(log: cache.ActionLogger, **kwargs):
    from cubed_tube.worker.worker import upload_user_writes
    queue_len = len(cache.DEFERRED_QUEUE)
    log.text(f'Uploading {queue_len} items')
    upload_user_writes()
    queue_len = len(cache.DEFERRED_QUEUE)
    log.text(f'Done! Current queue length: {queue_len} items')


def wait(seconds, **kwargs):
    time.sleep(seconds)


def create_promo(**kwargs):
    pass


def list_promos(**kwargs):
    pass


def list_actions(action: schemas.ActionRecord,
                 log: cache.ActionLogger, **kwargs):
    from cubed_tube.actions import actions
    output = ['<table>']
    for record in actions.list_action_records(action.user):
        action_time = datetime.utcfromtimestamp(record.time)
        params = html.escape(json.dumps({'action_id': record.id}))
        link = (
            f'<a href="#" data-action="fetch_action_logs" '
            f'data-params="{params}" class="action_link format_time" '
            f'title="{record.id}">'
            f'{record.time}</a>'
        )
        output.append(f'<tr><td>{link}</td><td>{record.action}</tr>')
    output.append('</table>')
    log.html(''.join(output))


def fetch_action_logs(
        action: schemas.ActionRecord, params: Dict, 
        log: cache.ActionLogger, **kwargs):
    from cubed_tube.actions import actions
    log.text(f'Fetching {params["action_id"]}')
    record = actions.find_action_record(action.user, params["action_id"])
    if not record:
        log.text('Action not found')
        return
    for log_entry in cache.ActionLogger(params["action_id"]).queue.get():
        log.log(**json.loads(log_entry))
    

def memcached_stats(params: Dict, log: cache.ActionLogger, **kwargs):
    args = []
    if params['args']:
        args = params['args'].split()
    log.pre_text('\n'.join(
        f'{key}: {val}' for key, val in cache.CLIENT.stats(*args).items()))


def memcached_keys(log: cache.ActionLogger, **kwargs):
    keys = {}
    for key, val in cache.CLIENT.stats('items').items():
        _, shard, subkey = util.ensure_str(key).split(':')
        if subkey != 'number' or val == 0:
            continue
        print(val, type(val))
        for rec, details in cache.CLIENT.stats('cachedump', shard, str(val + 10)).items():
            keys[util.ensure_str(rec)] = util.ensure_str(details)
        
    log.pre_text('\n'.join(f'{key}: {val}' for key, val in keys.items()))


def manage_videos(params: Dict, log: cache.ActionLogger, **kwargs):
    from cubed_tube.lib import models
    if not params.get('video_ids'):
        return
    video_ids_str = cast(str, params['video_ids']).strip()
    video_ids = [v for v in re.split(r'\s+', video_ids_str) if v != '-']

    with models.DATABASE as db:
        vids: List[models.Video] = models.Video.select().where(
            models.Video.video_id.in_(video_ids))
        if len(vids) != len(video_ids):
            missing = set(video_ids) - set(v.video_id for v in vids)
            log.text(f'Missing videos: [{", ".join(missing)}]')
            return
        log.text(f'Performing "{params["intent"]}" on {len(vids)} videos: '
                 f'[{", ".join(video_ids)}]')
        with db.atomic():
            if params['intent'] == 'move':
                for vid in vids:
                    vid.series = params['series']
                    vid.channel = params['channel']
                    vid.save()
            if params['intent'] == 'delete':
                now = time.time()
                for vid in vids:
                    vid.tombstone = now
                    vid.save()
            if params['intent'] == 'undelete':
                for vid in vids:
                    vid.tombstone = None
                    vid.save()
    log.text('Completed transaction, database closed')

