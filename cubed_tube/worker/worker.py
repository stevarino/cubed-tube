
from datetime import datetime
import json
import logging
from time import sleep
from typing import Optional

from prometheus_client import Gauge, start_http_server, Counter

from cubed_tube.lib import util, models
from cubed_tube.backend import cloud_storage
from cubed_tube.actions import actions
import cubed_tube.backend.memcached_client as cache


CNT_ERRORS = util.make_counter('ht_worker_errors', 'Number of errors')
CNT_WARNINGS = util.make_counter('ht_worker_warnings', 'Number of warnings')
CNT_UPLOADS = util.make_counter('ht_worker_uploads', 'Number of uploads')
GAU_DEFERRED = Gauge('ht_user_state_queue', 'Count of users in the queue.')
GAU_ACTIONS = Gauge('ht_actions', 'Count of action records in the cache.')
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


CLEANUP_ACTIONS_TIMER = util.Timer()
DEFERRED_USER_DATA_TIMER = util.Timer()


@util.cache_func
def check_user_writes():
    creds = util.load_credentials(ttl=30)
    write_frequency = creds.backend.memcache.write_frequency
    if not write_frequency:
        return

    queue_len = len(cache.DEFERRED_QUEUE)
    GAU_DEFERRED.set(queue_len)

    if not DEFERRED_USER_DATA_TIMER.is_ready(write_frequency, reset=False):
        return
    LOGGER.info(f'Scanning queue ({queue_len} items)')

    if not queue_len:
        return
    upload_user_writes()


def upload_user_writes():
    keys = cache.DEFERRED_QUEUE.clear()
    DEFERRED_USER_DATA_TIMER.reset()

    for chunked_keys in util.chunk(keys, len(keys), 50):
        contents = cache.CLIENT.get_many(chunked_keys)
        missing = set(chunked_keys) - set(contents.keys())
        if missing:
            LOGGER.warning(
                'Missing keys from get_many: %s', json.dumps(list(missing)))
            CNT_WARNINGS.inc()
        for key in contents:
            if not contents[key]:
                LOGGER.warning('Missing content for key %s', key)
                continue
            cloud_storage.put_object(key, contents[key])
            CNT_UPLOADS.inc()


def process_work_queue():
    while True:
        action = actions.dequeue_action_request()
        if not action:
            return
        LOGGER.info(f'Working on action {action.id}')
        actions.perform_action(action)
        LOGGER.info(f'Completed action {action.id}')


@util.cache_func
def cleanup_action_list():
    final_items = []
    records, cas = cache.CLIENT.gets(cache.ACTION_LIST.name)
    if not cas:
        LOGGER.warning('Missing ACTION_LIST in cache')
        CNT_WARNINGS.inc()
        return
    if not records:
        GAU_ACTIONS.set(0)
        return
    records = cache.MemcacheQueue._to_list(records)

    rec_len = len(records)
    GAU_ACTIONS.set(rec_len)

    if not CLEANUP_ACTIONS_TIMER.is_ready(3600) or not records:
        return

    items = [actions.ActionRecord.from_dict(json.loads(item))
             for item in records]
    record_mapping = {item.id: item for item in items}
    item_ids = list(record_mapping.keys())
    found = set()

    for chunked_keys in util.chunk(item_ids, len(items), 50):
        # log queue name to action id
        log_mapping = {cache.ActionLogger.queue_name(key): key
                       for key in chunked_keys}
        for log in cache.CLIENT.get_many(list(log_mapping.keys())).keys():
            # convert a log name to a action_id, and then to a record
            found.add(log_mapping[log])
            record = record_mapping[log_mapping[log]]
            final_items.append(json.dumps(record.as_dict()))

    LOGGER.info(
        f'Cleaned Action List: {rec_len - len(final_items)} of {rec_len}')
    cache.ACTION_LIST.set_cas(final_items, cas)


def loop():
    creds = util.load_credentials()
    start_http_server(creds.backend.worker_port or 3900)
    cache.create_client()
    LOGGER.info("Worker started")

    models.init_database()
    models.DATABASE.close()

    while True:
        try:
            check_user_writes(ttl=60)
        except Exception as e:
            CNT_ERRORS.inc()
            LOGGER.exception('Unhandled error during check_user_writes')
        process_work_queue()
        cleanup_action_list(ttl=60)
        sleep(1)


if __name__ == '__main__':
    # Start up the server to expose the metrics.
    loop()
